/**
 * Security utilities for handling sensitive data
 */

/**
 * Generate or retrieve encryption key using Web Crypto API
 */
async function getOrGenerateKey() {
  const keyName = 'executioner_encryption_key';
  
  // Try to get existing key from sessionStorage
  const storedKey = sessionStorage.getItem(keyName);
  if (storedKey) {
    const keyData = JSON.parse(storedKey);
    return await crypto.subtle.importKey(
      'jwk',
      keyData,
      { name: 'AES-GCM', length: 256 },
      true,
      ['encrypt', 'decrypt']
    );
  }
  
  // Generate new key
  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt', 'decrypt']
  );
  
  // Export and store key (for session only)
  const exportedKey = await crypto.subtle.exportKey('jwk', key);
  sessionStorage.setItem(keyName, JSON.stringify(exportedKey));
  
  return key;
}

/**
 * Encrypt sensitive data using Web Crypto API
 * Uses AES-GCM for authenticated encryption
 */
export async function encryptSensitiveData(value) {
  if (!value || typeof value !== 'string') return '';
  
  try {
    const encoder = new TextEncoder();
    const data = encoder.encode(value);
    
    // Generate random IV for each encryption
    const iv = crypto.getRandomValues(new Uint8Array(12));
    
    // Get or generate encryption key
    const key = await getOrGenerateKey();
    
    // Encrypt the data
    const encryptedData = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv },
      key,
      data
    );
    
    // Combine IV and encrypted data for storage
    const combined = new Uint8Array(iv.length + encryptedData.byteLength);
    combined.set(iv, 0);
    combined.set(new Uint8Array(encryptedData), iv.length);
    
    // Convert to base64 for storage
    return btoa(String.fromCharCode(...combined));
  } catch (e) {
    console.error('Encryption failed:', e);
    // Fallback to masking on error
    return maskSensitiveValue(value);
  }
}

/**
 * Decrypt sensitive data using Web Crypto API
 */
export async function decryptSensitiveData(encryptedValue) {
  if (!encryptedValue || typeof encryptedValue !== 'string') return '';
  
  try {
    // Decode from base64
    const combined = Uint8Array.from(atob(encryptedValue), c => c.charCodeAt(0));
    
    // Extract IV and encrypted data
    const iv = combined.slice(0, 12);
    const encryptedData = combined.slice(12);
    
    // Get encryption key
    const key = await getOrGenerateKey();
    
    // Decrypt the data
    const decryptedData = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv },
      key,
      encryptedData
    );
    
    // Convert back to string
    const decoder = new TextDecoder();
    return decoder.decode(decryptedData);
  } catch (e) {
    console.error('Decryption failed:', e);
    // Return masked value on error
    return '********';
  }
}

/**
 * Legacy functions for backward compatibility
 * These now use the secure encryption methods
 */
export function obfuscateSensitiveData(value) {
  console.warn('obfuscateSensitiveData is deprecated. Use encryptSensitiveData instead.');
  // Return a promise-wrapped result for sync compatibility
  return encryptSensitiveData(value).then(result => result).catch(() => '********');
}

export function deobfuscateSensitiveData(value) {
  console.warn('deobfuscateSensitiveData is deprecated. Use decryptSensitiveData instead.');
  // Return a promise-wrapped result for sync compatibility
  return decryptSensitiveData(value).then(result => result).catch(() => '********');
}

/**
 * Check if a field name indicates sensitive data
 */
export function isSensitiveField(fieldName) {
  if (!fieldName || typeof fieldName !== 'string') return false;
  
  const sensitivePatterns = [
    'password',
    'secret',
    'token',
    'key',
    'private',
    'api_key',
    'auth',
    'credential',
    'certificate',
    'ssh',
  ];
  
  const lowerFieldName = fieldName.toLowerCase();
  return sensitivePatterns.some(pattern => lowerFieldName.includes(pattern));
}

/**
 * Mask sensitive data for display
 */
export function maskSensitiveValue(value, showFirst = 0, showLast = 0) {
  if (!value || typeof value !== 'string') return '';
  
  const length = value.length;
  if (length <= showFirst + showLast) {
    return '*'.repeat(length);
  }
  
  const firstPart = showFirst > 0 ? value.slice(0, showFirst) : '';
  const lastPart = showLast > 0 ? value.slice(-showLast) : '';
  const maskedPart = '*'.repeat(Math.max(8, length - showFirst - showLast));
  
  return firstPart + maskedPart + lastPart;
}

/**
 * Sanitize object by masking sensitive fields
 */
export function sanitizeObject(obj, deep = true) {
  if (!obj || typeof obj !== 'object') return obj;
  
  const sanitized = Array.isArray(obj) ? [] : {};
  
  for (const [key, value] of Object.entries(obj)) {
    if (isSensitiveField(key)) {
      sanitized[key] = maskSensitiveValue(String(value));
    } else if (deep && typeof value === 'object' && value !== null) {
      sanitized[key] = sanitizeObject(value, deep);
    } else {
      sanitized[key] = value;
    }
  }
  
  return sanitized;
}

/**
 * Generate a secure random ID
 */
export function generateSecureId(prefix = '') {
  const randomBytes = new Uint8Array(16);
  crypto.getRandomValues(randomBytes);
  const hex = Array.from(randomBytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  
  return prefix ? `${prefix}_${hex}` : hex;
}

/**
 * Validate URL for security
 */
export function validateUrl(url) {
  if (!url || typeof url !== 'string') {
    return { valid: false, error: 'URL is required' };
  }
  
  try {
    const parsed = new URL(url);
    
    // Check for dangerous protocols
    const allowedProtocols = ['http:', 'https:'];
    if (!allowedProtocols.includes(parsed.protocol)) {
      return { 
        valid: false, 
        error: `Invalid protocol. Only ${allowedProtocols.join(', ')} are allowed` 
      };
    }
    
    // Check for localhost/private IPs in production
    const privatePatterns = [
      /^localhost$/i,
      /^127\./,
      /^10\./,
      /^172\.(1[6-9]|2[0-9]|3[0-1])\./,
      /^192\.168\./,
      /^169\.254\./,
      /^::1$/,
      /^fc00:/i,
      /^fe80:/i,
    ];
    
    // In production, you might want to block private IPs
    const isPrivate = privatePatterns.some(pattern => pattern.test(parsed.hostname));
    
    return { 
      valid: true, 
      sanitized: url,
      warning: isPrivate ? 'URL points to a private/local address' : null
    };
  } catch (e) {
    return { valid: false, error: 'Invalid URL format' };
  }
}

/**
 * Sanitize HTML to prevent XSS
 */
export function sanitizeHtml(html) {
  if (!html || typeof html !== 'string') return '';
  
  // Create a temporary element to parse HTML
  const temp = document.createElement('div');
  temp.textContent = html;
  return temp.innerHTML;
}

/**
 * Check if a command is potentially dangerous
 */
export function isCommandDangerous(command) {
  if (!command || typeof command !== 'string') return false;
  
  const dangerousPatterns = [
    // System destruction
    /rm\s+-rf\s+\//gi,
    /dd\s+if=.*of=\/dev\//gi,
    /mkfs\./gi,
    
    // Fork bombs
    /:\(\)\{.*\|.*&\};/g,
    
    // Network attacks
    /nc\s+-l/gi,
    /nmap/gi,
    
    // Privilege escalation
    /chmod\s+777\s+\//gi,
    /chmod\s+\+s/gi,
    
    // Code execution from internet
    /curl.*\|\s*(sh|bash)/gi,
    /wget.*\|\s*(sh|bash)/gi,
    
    // Password/key extraction
    /cat\s+.*\/(shadow|passwd|ssh)/gi,
    /find.*-name.*\.(key|pem|password)/gi,
  ];
  
  return dangerousPatterns.some(pattern => pattern.test(command));
}

/**
 * Create a Content Security Policy header value
 */
export function generateCSP() {
  return {
    'default-src': ["'self'"],
    'script-src': ["'self'", "'unsafe-inline'"], // unsafe-inline needed for Vue
    'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
    'font-src': ["'self'", 'https://fonts.gstatic.com'],
    'img-src': ["'self'", 'data:', 'https:'],
    'connect-src': ["'self'"],
    'frame-ancestors': ["'none'"],
    'form-action': ["'self'"],
    'base-uri': ["'self'"],
  };
}

/**
 * Format CSP for header
 */
export function formatCSP(csp) {
  return Object.entries(csp)
    .map(([key, values]) => `${key} ${values.join(' ')}`)
    .join('; ');
}

/**
 * Validate and sanitize file uploads
 */
export function validateFileUpload(file, options = {}) {
  const {
    maxSize = 10 * 1024 * 1024, // 10MB default
    allowedTypes = ['application/json', 'text/plain'],
    allowedExtensions = ['.json', '.txt', '.yml', '.yaml']
  } = options;
  
  const errors = [];
  
  // Check file size
  if (file.size > maxSize) {
    errors.push(`File size exceeds maximum of ${maxSize / 1024 / 1024}MB`);
  }
  
  // Check file type
  if (allowedTypes.length > 0 && !allowedTypes.includes(file.type)) {
    errors.push(`File type not allowed. Allowed types: ${allowedTypes.join(', ')}`);
  }
  
  // Check file extension
  const extension = '.' + file.name.split('.').pop().toLowerCase();
  if (allowedExtensions.length > 0 && !allowedExtensions.includes(extension)) {
    errors.push(`File extension not allowed. Allowed: ${allowedExtensions.join(', ')}`);
  }
  
  // Check for suspicious patterns in filename
  const suspiciousPatterns = [
    /\.\./,  // Directory traversal
    /[<>:"|?*]/,  // Invalid characters
    /^\./, // Hidden files
  ];
  
  if (suspiciousPatterns.some(pattern => pattern.test(file.name))) {
    errors.push('Filename contains invalid characters');
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Create secure storage wrapper
 */
export class SecureStorage {
  constructor(storageType = 'localStorage') {
    this.storage = window[storageType];
    this.prefix = 'executioner_secure_';
  }
  
  setItem(key, value, sensitive = false) {
    const storageKey = this.prefix + key;
    let storageValue = JSON.stringify(value);
    
    if (sensitive) {
      storageValue = obfuscateSensitiveData(storageValue);
    }
    
    try {
      this.storage.setItem(storageKey, storageValue);
      return true;
    } catch (e) {
      console.error('Storage error:', e);
      return false;
    }
  }
  
  getItem(key, sensitive = false) {
    const storageKey = this.prefix + key;
    let storageValue = this.storage.getItem(storageKey);
    
    if (!storageValue) return null;
    
    try {
      if (sensitive) {
        storageValue = deobfuscateSensitiveData(storageValue);
      }
      return JSON.parse(storageValue);
    } catch (e) {
      console.error('Storage retrieval error:', e);
      return null;
    }
  }
  
  removeItem(key) {
    const storageKey = this.prefix + key;
    this.storage.removeItem(storageKey);
  }
  
  clear() {
    // Only clear our prefixed items
    const keys = [];
    for (let i = 0; i < this.storage.length; i++) {
      const key = this.storage.key(i);
      if (key.startsWith(this.prefix)) {
        keys.push(key);
      }
    }
    keys.forEach(key => this.storage.removeItem(key));
  }
}