import '@testing-library/jest-dom/vitest';

Object.defineProperties(HTMLDialogElement.prototype, {
  showModal: { configurable: true, writable: true, value() { this.setAttribute('open', ''); } },
  close: { configurable: true, writable: true, value() { this.removeAttribute('open'); } },
});
