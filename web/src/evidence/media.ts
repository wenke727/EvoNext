type ReadMedia = (
  snapshot: string,
  path: string,
  signal: AbortSignal,
) => Promise<Blob>;
type Entry = {
  snapshot: string;
  path: string;
  controller: AbortController;
  users: number;
  promise: Promise<Blob>;
  resolve: (blob: Blob) => void;
  reject: (error: unknown) => void;
  blob?: Blob;
};

// Snapshot identity includes the byte manifest. Paths are never fetched as arbitrary URLs.
export class MediaCache {
  private entries = new Map<string, Entry>();
  private queue: Entry[] = [];
  private active = 0;
  private disposed = false;

  constructor(
    private readonly read: ReadMedia,
    private readonly concurrency = 4,
    private readonly maxBytes = 32 * 1024 * 1024,
    private readonly maxItems = 48,
  ) {}

  acquire(snapshot: string, path: string) {
    if (this.disposed) throw new Error("Media session closed");
    const key = JSON.stringify([snapshot, path]);
    let entry = this.entries.get(key);
    if (!entry) {
      let resolve!: Entry["resolve"];
      let reject!: Entry["reject"];
      const promise = new Promise<Blob>((yes, no) => {
        resolve = yes;
        reject = no;
      });
      entry = {
        snapshot,
        path,
        controller: new AbortController(),
        users: 0,
        promise,
        resolve,
        reject,
      };
      this.entries.set(key, entry);
      this.queue.push(entry);
    }
    this.entries.delete(key);
    this.entries.set(key, entry);
    entry.users++;
    this.pump();
    const owned = entry;
    let released = false;
    return {
      promise: owned.promise,
      release: () => {
        if (released) return;
        released = true;
        owned.users--;
        if (!owned.users && !owned.blob) {
          owned.controller.abort();
          owned.reject(
            new DOMException("Media no longer visible", "AbortError"),
          );
          if (this.entries.get(key) === owned) this.entries.delete(key);
          this.queue = this.queue.filter((item) => item !== owned);
        }
        this.prune();
      },
    };
  }

  dispose() {
    this.disposed = true;
    for (const entry of this.entries.values()) {
      entry.controller.abort();
      entry.reject(new DOMException("Media session closed", "AbortError"));
    }
    this.entries.clear();
    this.queue = [];
  }

  private pump() {
    while (
      !this.disposed &&
      this.active < this.concurrency &&
      this.queue.length
    ) {
      const entry = this.queue.shift()!;
      if (entry.controller.signal.aborted) continue;
      this.active++;
      // Catch synchronous reader failures as well as rejected network requests.
      Promise.resolve()
        .then(() =>
          this.read(entry.snapshot, entry.path, entry.controller.signal),
        )
        .then((blob) => {
          if (entry.controller.signal.aborted) return;
          entry.blob = blob;
          entry.resolve(blob);
        })
        .catch((error) => {
          const key = JSON.stringify([entry.snapshot, entry.path]);
          if (this.entries.get(key) === entry) this.entries.delete(key);
          entry.reject(error);
        })
        .finally(() => {
          this.active--;
          this.prune();
          this.pump();
        });
    }
  }

  private prune() {
    let bytes = 0;
    let count = 0;
    for (const entry of this.entries.values())
      if (entry.blob) {
        bytes += entry.blob.size;
        count++;
      }
    for (const [key, entry] of this.entries) {
      if (bytes <= this.maxBytes && count <= this.maxItems) break;
      if (!entry.users && entry.blob) {
        bytes -= entry.blob.size;
        count--;
        this.entries.delete(key);
      }
    }
  }
}
