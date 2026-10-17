// Decorative image failures never obscure the story or its controls.
document.querySelectorAll('[data-story-media]').forEach(frame => {
  const image = frame.querySelector('img');
  const unavailable = () => {
    image.hidden = true;
    frame.classList.add('media-unavailable');
    frame.querySelector('.image-unavailable').hidden = false;
  };
  image.addEventListener('error', unavailable, { once: true });
  if (image.complete && image.naturalWidth === 0) unavailable();
});
