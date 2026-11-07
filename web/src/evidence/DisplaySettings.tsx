import { useEffect, useRef } from "react";
import { DISPLAY_OPTIONS, readDisplayPreferences, type DisplayKey, type DisplayPreferences } from "./display-preferences";

export function DisplaySettings({ open, value, onChange, onClose }: {
  open: boolean;
  value: DisplayPreferences;
  onChange: (next: DisplayPreferences) => void;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);

  function toggle(key: DisplayKey, checked: boolean) {
    onChange({ ...value, [key]: checked });
  }
  return (
    <dialog ref={dialog} className="display-settings" aria-labelledby="display-settings-title" onClose={onClose}>
      <div className="dialog-heading">
        <h2 id="display-settings-title">显示选项</h2>
        <button autoFocus onClick={onClose}>关闭</button>
      </div>
      <p className="display-settings-note">仅调整显示，在此浏览器跨任务保留。</p>
      {["轨迹视图", "任务信息", "步骤字段"].map(group => (
        <fieldset key={group}>
          <legend>{group}</legend>
          {DISPLAY_OPTIONS.filter(option => option.group === group).map(option => (
            <label key={option.key}>
              <span>{option.label}</span>
              <input type="checkbox" checked={value[option.key]} onChange={event => toggle(option.key, event.target.checked)} />
            </label>
          ))}
        </fieldset>
      ))}
      <button className="quiet" onClick={() => onChange(readDisplayPreferences(null))}>恢复默认显示</button>
    </dialog>
  );
}
