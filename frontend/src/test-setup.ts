import "@testing-library/jest-dom/vitest"

// jsdom does not implement matchMedia, which the theme provider depends on.
// Default to "light" so tests are deterministic; individual tests override it.
if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}
