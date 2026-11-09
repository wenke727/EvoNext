import { useEffect, useRef } from "react";
import type { Preferences } from "./preferences";
import { DISPLAY_OPTIONS, readDisplayPreferences, type DisplayKey, type DisplayPreferences } from "./display-preferences";

type Layout = Pick<Preferences, "markers" | "space" | "dock">;

export function DisplaySettings({ open, value, layout, onLayoutChange, onChange, onClose }: {
  open: boolean;
  layout: Layout;
  onLayoutChange: (next: Partial<Layout>) => void;
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
          {group === "轨迹视图" && <>
            <label><span>动作标记</span><input type="checkbox" checked={layout.markers} onChange={event => onLayoutChange({markers:event.target.checked})} /></label>
            <label><span>坐标空间</span><select aria-label="动作坐标空间" value={layout.space} onChange={event => onLayoutChange({space:event.target.value as Layout["space"]})}>
              <option value="normalized">0–1000</option><option value="pixels">原图像素</option><option value="unknown">未声明</option>
            </select></label>
            <label><span>小图条位置</span><select aria-label="小图条位置" value={layout.dock} onChange={event => onLayoutChange({dock:event.target.value as Layout["dock"]})}>
              <option value="top">上方</option><option value="bottom">下方</option>
            </select></label>
          </>}
          {DISPLAY_OPTIONS.filter(option => option.group === group).map(option => (
            <label key={option.key}>
              <span>{option.label}</span>
              <input type="checkbox" checked={value[option.key]} onChange={event => toggle(option.key, event.target.checked)} />
            </label>
          ))}
        </fieldset>
      ))}
      <button className="quiet" onClick={() => { onChange(readDisplayPreferences(null)); onLayoutChange({markers:true,space:"normalized",dock:"top"}); }}>恢复默认显示</button>
    </dialog>
  );
}
