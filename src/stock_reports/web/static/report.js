// Fit the native PDF viewer to its panel, including narrow mobile screens.
const frame = document.querySelector('.pdf-panel iframe');
if (frame) {
  const url = new URL(frame.src);
  let previous = 0;
  let timer;
  const fit = () => {
    const zoom = Math.max(20, Math.min(100, Math.floor((frame.clientWidth - 32) / 794 * 100)));
    if (zoom === previous) return;
    previous = zoom;
    url.hash = 'zoom=' + zoom + '&pagemode=none';
    frame.src = url.href;
  };
  fit();
  window.addEventListener('resize', () => {
    clearTimeout(timer);
    timer = setTimeout(fit, 250);
  });
}
