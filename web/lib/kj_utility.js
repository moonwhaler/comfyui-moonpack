// Derived from ComfyUI-KJNodes by kijai (https://github.com/kijai/ComfyUI-KJNodes, commit ab72eda), GPL-3.0.
// Modified for MoonPack (GPL-3.0): see the MoonPack git history for changes.

const { app } = window.comfyAPI.app;

// ─── General-purpose helpers shared across KJNodes JS ───

export function chainCallback(object, property, callback) {
  if (object == undefined) {
    console.error("Tried to add callback to non-existant object")
    return;
  }
  if (property in object) {
    const callback_orig = object[property]
    object[property] = function () {
      const r = callback_orig.apply(this, arguments);
      callback.apply(this, arguments);
      return r
    };
  } else {
    object[property] = callback;
  }
}

// ─── Graph coordinate helpers ───

// ─── Middle-click pan passthrough for DOM widgets ───
// Allows panning the LiteGraph canvas via middle-click drag on any DOM element
export function addMiddleClickPan(element) {
  const onMouseDown = (e) => {
    if (e.button !== 1) return;
    e.preventDefault();
    const ds = app.canvas?.ds;
    if (!ds) return;
    const startX = e.clientX, startY = e.clientY;
    const startOffsetX = ds.offset[0], startOffsetY = ds.offset[1];
    const onMove = (me) => {
      const scale = ds.scale || 1;   // offset is graph-space; LiteGraph pans by (screen delta / scale)
      ds.offset[0] = startOffsetX + (me.clientX - startX) / scale;
      ds.offset[1] = startOffsetY + (me.clientY - startY) / scale;
      app.canvas.setDirty(true, true);
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };
  element.addEventListener('mousedown', onMouseDown);
  return () => element.removeEventListener('mousedown', onMouseDown);
}

// The widget holding a loader's input file: Load Image "image", VHS-style "video", core Load Video "file"
const sourceFileWidget = (srcNode) => srcNode.widgets?.find((w) => w.name === "image" || w.name === "video" || (w.name === "file" && srcNode.comfyClass === "LoadVideo"));

// ─── Resolve preview image/video from a connected source node ───
// Walks the graph link to find what's connected to node.inputs[inputSlot]
// and returns { url, isVideo, videoEl } or null
export function resolveSourcePreview(node, inputSlot) {
  if (!node.graph) return null;
  const input = node.inputs?.[inputSlot];
  if (!input || input.link == null) return null;
  const link = node.graph.links?.get(input.link);
  if (!link) return null;
  const srcNode = node.graph.getNodeById(link.origin_id);
  if (!srcNode) return null;

  // Check for VHS-style video preview widget
  const vpWidget = srcNode.widgets?.find((w) => w.name === "videopreview");
  if (vpWidget?.videoEl?.src) {
    return { isVideo: true, videoEl: vpWidget.videoEl };
  }

  const w = sourceFileWidget(srcNode);
  if (w?.value) {
    let subfolder = "", fname = w.value;
    const lastSlash = fname.lastIndexOf("/");
    if (lastSlash >= 0) { subfolder = fname.substring(0, lastSlash); fname = fname.substring(lastSlash + 1); }
    const isVideo = w.name !== "image";
    const url = `/view?filename=${encodeURIComponent(fname)}&type=input&subfolder=${encodeURIComponent(subfolder)}`;
    return { url, isVideo };
  }

  // Fallback: check node.imgs (set after execution)
  if (srcNode.imgs?.length > 0 && srcNode.imgs[0].src) {
    return { url: srcNode.imgs[0].src, isVideo: false };
  }
  return null;
}

// ─── Source input watcher ───
// Watches IMAGE inputs for connection changes and source widget changes.
// Calls onChange(sources) when connections change or the source node's image/video widget changes.
// inputName: an input name, a predicate (input) => bool, or null for every IMAGE input.
// sources: array of { url, isVideo, videoEl, name } per connected matching input (name = that input's name).
// Returns a cleanup function.
export function watchImageInputs(node, inputName, onChange) {
  let watchedWidgets = [];
  const matches = (inp) => typeof inputName === "function" ? inputName(inp) : inputName ? inp.name === inputName : inp.type === "IMAGE";
  const matchingSlots = () => node.inputs.map((inp, i) => matches(inp) ? i : -1).filter(i => i >= 0);

  function unwatchWidgets() {
    for (const { widget, origCb } of watchedWidgets) widget.callback = origCb;
    watchedWidgets = [];
  }

  function resolve() {
    if (!node.inputs) return [];
    return matchingSlots().map(i => {
      const s = resolveSourcePreview(node, i);
      return s && { ...s, name: node.inputs[i].name };
    }).filter(s => s);
  }

  function watch() {
    unwatchWidgets();
    if (!node.inputs || !node.graph) return;
    const slots = matchingSlots();
    for (const slotIdx of slots) {
      const input = node.inputs[slotIdx];
      if (!input || input.link == null) continue;
      const link = node.graph.links?.get(input.link);
      if (!link) continue;
      const srcNode = node.graph.getNodeById(link.origin_id);
      if (!srcNode) continue;
      const w = sourceFileWidget(srcNode);
      if (!w) continue;
      const origCb = w.callback;
      w.callback = function (...args) {
        if (origCb) origCb.apply(this, args);
        setTimeout(() => onChange(resolve()), 100);
      };
      watchedWidgets.push({ widget: w, origCb });
    }
  }

  chainCallback(node, "onConnectionsChange", function (type) {
    // Only react to input connection changes, not output
    if (type != null && type !== 1) return;
    setTimeout(() => {
      watch();
      onChange(resolve());
    }, 100);
  });

  chainCallback(node, "onRemoved", unwatchWidgets);

  return unwatchWidgets;
}

// ─── Video frame capture ───
// Draws the current frame of a video element to a fresh canvas at native resolution.
// If the video isn't decoded yet (readyState < 2), waits once for "loadeddata" before capturing.
// Calls callback(canvas) with the resulting canvas. Caller decides whether to use it directly
// (drawImage accepts canvas) or convert via toDataURL.
export function captureVideoFrame(videoEl, callback) {
  const capture = () => {
    if (!videoEl.videoWidth || !videoEl.videoHeight) return;
    const c = document.createElement("canvas");
    c.width = videoEl.videoWidth;
    c.height = videoEl.videoHeight;
    c.getContext("2d").drawImage(videoEl, 0, 0);
    callback(c);
  };
  if (videoEl.readyState >= 2) {
    capture();
  } else {
    const onReady = () => { videoEl.removeEventListener("loadeddata", onReady); capture(); };
    videoEl.addEventListener("loadeddata", onReady);
  }
}

// Returns the appropriate CSS cursor for a bbox hit mode string.
export function cursorForBboxMode(mode) {
  if (mode === "move") return "move";
  if (mode === "resize-tl" || mode === "resize-br") return "nwse-resize";
  if (mode === "resize-tr" || mode === "resize-bl") return "nesw-resize";
  if (mode === "resize-t" || mode === "resize-b") return "ns-resize";
  if (mode === "resize-l" || mode === "resize-r") return "ew-resize";
  return null;
}

// ─── Wheel zoom passthrough for DOM widgets ───
// Re-dispatches wheel events to the LiteGraph canvas for zoom
export function addWheelPassthrough(element) {
  element.addEventListener("wheel", (e) => {
    const gc = document.getElementById("graph-canvas");
    if (gc) {
      gc.dispatchEvent(new WheelEvent(e.type, e));
      e.preventDefault();
    }
  }, { passive: false });
}

