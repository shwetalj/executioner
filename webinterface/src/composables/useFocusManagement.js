/**
 * Focus management composable for accessibility
 * Manages focus trapping, restoration, and keyboard navigation
 */

import { ref, nextTick } from 'vue';

/**
 * Trap focus within an element (useful for modals)
 */
export function useFocusTrap(containerRef) {
  const previouslyFocusedElement = ref(null);
  
  const focusableSelectors = [
    'a[href]',
    'button:not([disabled])',
    'textarea:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    '[tabindex]:not([tabindex="-1"])'
  ];
  
  const getFocusableElements = () => {
    if (!containerRef.value) return [];
    return Array.from(
      containerRef.value.querySelectorAll(focusableSelectors.join(','))
    );
  };
  
  const trapFocus = (event) => {
    const focusableElements = getFocusableElements();
    if (focusableElements.length === 0) return;
    
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    
    if (event.key === 'Tab') {
      if (event.shiftKey) {
        // Shift + Tab
        if (document.activeElement === firstElement) {
          event.preventDefault();
          lastElement.focus();
        }
      } else {
        // Tab
        if (document.activeElement === lastElement) {
          event.preventDefault();
          firstElement.focus();
        }
      }
    }
    
    // Escape key to close
    if (event.key === 'Escape') {
      restoreFocus();
    }
  };
  
  const activate = () => {
    // Store currently focused element
    previouslyFocusedElement.value = document.activeElement;
    
    // Focus first focusable element
    nextTick(() => {
      const focusableElements = getFocusableElements();
      if (focusableElements.length > 0) {
        focusableElements[0].focus();
      }
    });
    
    // Add event listener
    document.addEventListener('keydown', trapFocus);
  };
  
  const deactivate = () => {
    document.removeEventListener('keydown', trapFocus);
    restoreFocus();
  };
  
  const restoreFocus = () => {
    if (previouslyFocusedElement.value) {
      previouslyFocusedElement.value.focus();
      previouslyFocusedElement.value = null;
    }
  };
  
  return {
    activate,
    deactivate,
    restoreFocus
  };
}

/**
 * Skip navigation link for screen readers
 */
export function useSkipLinks() {
  const skipToMain = () => {
    const main = document.querySelector('[role="main"]');
    if (main) {
      main.tabIndex = -1;
      main.focus();
      main.scrollIntoView();
    }
  };
  
  const skipToNavigation = () => {
    const nav = document.querySelector('[role="navigation"]');
    if (nav) {
      nav.tabIndex = -1;
      nav.focus();
    }
  };
  
  return {
    skipToMain,
    skipToNavigation
  };
}

/**
 * Roving tabindex for lists (arrow key navigation)
 */
export function useRovingTabindex(itemsRef, options = {}) {
  const currentIndex = ref(0);
  const { orientation = 'vertical', loop = true } = options;
  
  const handleKeydown = (event) => {
    const items = itemsRef.value;
    if (!items || items.length === 0) return;
    
    let nextIndex = currentIndex.value;
    const lastIndex = items.length - 1;
    
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowRight':
        if (orientation === 'vertical' && event.key === 'ArrowRight') return;
        if (orientation === 'horizontal' && event.key === 'ArrowDown') return;
        
        event.preventDefault();
        nextIndex = currentIndex.value + 1;
        if (nextIndex > lastIndex) {
          nextIndex = loop ? 0 : lastIndex;
        }
        break;
        
      case 'ArrowUp':
      case 'ArrowLeft':
        if (orientation === 'vertical' && event.key === 'ArrowLeft') return;
        if (orientation === 'horizontal' && event.key === 'ArrowUp') return;
        
        event.preventDefault();
        nextIndex = currentIndex.value - 1;
        if (nextIndex < 0) {
          nextIndex = loop ? lastIndex : 0;
        }
        break;
        
      case 'Home':
        event.preventDefault();
        nextIndex = 0;
        break;
        
      case 'End':
        event.preventDefault();
        nextIndex = lastIndex;
        break;
        
      default:
        return;
    }
    
    // Update tabindex
    items[currentIndex.value].tabIndex = -1;
    items[nextIndex].tabIndex = 0;
    items[nextIndex].focus();
    currentIndex.value = nextIndex;
  };
  
  const initialize = () => {
    const items = itemsRef.value;
    if (!items || items.length === 0) return;
    
    // Set initial tabindex
    items.forEach((item, index) => {
      item.tabIndex = index === 0 ? 0 : -1;
      item.addEventListener('keydown', handleKeydown);
      
      // Update current index on focus
      item.addEventListener('focus', () => {
        currentIndex.value = index;
      });
    });
  };
  
  const cleanup = () => {
    const items = itemsRef.value;
    if (!items) return;
    
    items.forEach(item => {
      item.removeEventListener('keydown', handleKeydown);
    });
  };
  
  return {
    initialize,
    cleanup,
    currentIndex
  };
}

/**
 * Announce messages to screen readers
 */
export function useAnnouncer() {
  let announcer = null;
  
  const createAnnouncer = () => {
    if (!announcer) {
      announcer = document.createElement('div');
      announcer.setAttribute('role', 'status');
      announcer.setAttribute('aria-live', 'polite');
      announcer.setAttribute('aria-atomic', 'true');
      announcer.className = 'sr-only';
      document.body.appendChild(announcer);
    }
    return announcer;
  };
  
  const announce = (message, priority = 'polite') => {
    const element = createAnnouncer();
    element.setAttribute('aria-live', priority);
    
    // Clear and set message
    element.textContent = '';
    setTimeout(() => {
      element.textContent = message;
    }, 100);
  };
  
  const cleanup = () => {
    if (announcer && announcer.parentNode) {
      announcer.parentNode.removeChild(announcer);
      announcer = null;
    }
  };
  
  return {
    announce,
    cleanup
  };
}