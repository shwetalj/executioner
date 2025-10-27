/**
 * Composable for managing event listeners with automatic cleanup
 * Prevents memory leaks by ensuring all listeners are removed on component unmount
 */

import { onMounted, onBeforeUnmount, ref } from 'vue';

/**
 * Automatically manages event listener lifecycle
 * @param {EventTarget} target - The target element or window/document
 * @param {string} event - The event name
 * @param {Function} handler - The event handler function
 * @param {Object} options - addEventListener options
 */
export function useEventListener(target, event, handler, options = {}) {
  // Track if listener is active
  const isActive = ref(false);

  // Store the actual handler (in case we need to wrap it)
  let actualHandler = handler;

  // Add event listener
  const add = () => {
    if (!isActive.value && target) {
      target.addEventListener(event, actualHandler, options);
      isActive.value = true;
    }
  };

  // Remove event listener
  const remove = () => {
    if (isActive.value && target) {
      target.removeEventListener(event, actualHandler, options);
      isActive.value = false;
    }
  };

  // Auto-add on mount if target exists
  onMounted(() => {
    add();
  });

  // Auto-remove on unmount
  onBeforeUnmount(() => {
    remove();
  });

  return {
    add,
    remove,
    isActive
  };
}

/**
 * Manage multiple event listeners
 */
export function useEventListeners() {
  const listeners = ref([]);

  /**
   * Add an event listener with automatic cleanup
   */
  const addEventListener = (target, event, handler, options = {}) => {
    const listener = {
      target,
      event,
      handler,
      options,
      active: false
    };

    // Add the listener
    if (target) {
      target.addEventListener(event, handler, options);
      listener.active = true;
      listeners.value.push(listener);
    }

    // Return remove function
    return () => {
      removeEventListener(listener);
    };
  };

  /**
   * Remove a specific event listener
   */
  const removeEventListener = (listener) => {
    if (listener.active && listener.target) {
      listener.target.removeEventListener(
        listener.event,
        listener.handler,
        listener.options
      );
      listener.active = false;
      
      // Remove from array
      const index = listeners.value.indexOf(listener);
      if (index > -1) {
        listeners.value.splice(index, 1);
      }
    }
  };

  /**
   * Remove all event listeners
   */
  const removeAllEventListeners = () => {
    listeners.value.forEach(listener => {
      if (listener.active && listener.target) {
        listener.target.removeEventListener(
          listener.event,
          listener.handler,
          listener.options
        );
        listener.active = false;
      }
    });
    listeners.value = [];
  };

  // Cleanup on unmount
  onBeforeUnmount(() => {
    removeAllEventListeners();
  });

  return {
    addEventListener,
    removeEventListener,
    removeAllEventListeners,
    listeners
  };
}

/**
 * Keyboard shortcut management
 */
export function useKeyboardShortcut(key, handler, options = {}) {
  const {
    ctrl = false,
    alt = false,
    shift = false,
    meta = false,
    preventDefault = true,
    target = window
  } = options;

  const keyHandler = (event) => {
    // Check if all required modifiers match
    if (
      event.key === key &&
      event.ctrlKey === ctrl &&
      event.altKey === alt &&
      event.shiftKey === shift &&
      event.metaKey === meta
    ) {
      if (preventDefault) {
        event.preventDefault();
      }
      handler(event);
    }
  };

  return useEventListener(target, 'keydown', keyHandler);
}

/**
 * Resize observer with cleanup
 */
export function useResizeObserver(target, callback) {
  let observer = null;
  const isObserving = ref(false);

  const observe = () => {
    if (!observer && typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(callback);
    }

    if (observer && target && !isObserving.value) {
      const element = typeof target === 'function' ? target() : target;
      if (element) {
        observer.observe(element);
        isObserving.value = true;
      }
    }
  };

  const unobserve = () => {
    if (observer && isObserving.value) {
      observer.disconnect();
      isObserving.value = false;
    }
  };

  onMounted(() => {
    observe();
  });

  onBeforeUnmount(() => {
    unobserve();
    if (observer) {
      observer = null;
    }
  });

  return {
    observe,
    unobserve,
    isObserving
  };
}

/**
 * Intersection observer with cleanup
 */
export function useIntersectionObserver(target, callback, options = {}) {
  let observer = null;
  const isObserving = ref(false);

  const observe = () => {
    if (!observer && typeof IntersectionObserver !== 'undefined') {
      observer = new IntersectionObserver(callback, options);
    }

    if (observer && target && !isObserving.value) {
      const element = typeof target === 'function' ? target() : target;
      if (element) {
        observer.observe(element);
        isObserving.value = true;
      }
    }
  };

  const unobserve = () => {
    if (observer && isObserving.value) {
      observer.disconnect();
      isObserving.value = false;
    }
  };

  onMounted(() => {
    observe();
  });

  onBeforeUnmount(() => {
    unobserve();
    if (observer) {
      observer = null;
    }
  });

  return {
    observe,
    unobserve,
    isObserving
  };
}

/**
 * Mouse position tracking
 */
export function useMousePosition() {
  const x = ref(0);
  const y = ref(0);

  const updatePosition = (event) => {
    x.value = event.clientX;
    y.value = event.clientY;
  };

  useEventListener(window, 'mousemove', updatePosition);

  return { x, y };
}

/**
 * Click outside detection
 */
export function useClickOutside(elementRef, handler) {
  const listener = (event) => {
    const element = elementRef.value;
    if (!element || element.contains(event.target)) {
      return;
    }
    handler(event);
  };

  useEventListener(document, 'click', listener, true);
  useEventListener(document, 'touchstart', listener, true);
}

/**
 * Debounced event handler
 */
export function useDebouncedEvent(target, event, handler, delay = 300, options = {}) {
  let timeoutId = null;

  const debouncedHandler = (...args) => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => {
      handler(...args);
      timeoutId = null;
    }, delay);
  };

  const cleanup = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  onBeforeUnmount(cleanup);

  return useEventListener(target, event, debouncedHandler, options);
}

/**
 * Throttled event handler
 */
export function useThrottledEvent(target, event, handler, delay = 300, options = {}) {
  let lastCall = 0;
  let timeoutId = null;

  const throttledHandler = (...args) => {
    const now = Date.now();
    const timeSinceLastCall = now - lastCall;

    if (timeSinceLastCall >= delay) {
      handler(...args);
      lastCall = now;
    } else {
      // Schedule a call for the remaining time
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      timeoutId = setTimeout(() => {
        handler(...args);
        lastCall = Date.now();
        timeoutId = null;
      }, delay - timeSinceLastCall);
    }
  };

  const cleanup = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  onBeforeUnmount(cleanup);

  return useEventListener(target, event, throttledHandler, options);
}