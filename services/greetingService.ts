/**
 * Greeting Service
 * Pre-generates and caches greeting audio for immediate playback
 */

interface CachedGreeting {
    text: string;
    audioBase64: string;
    timestamp: number;
    userName?: string;
}

const GREETING_CACHE_KEY = 'zeno_greeting_cache';
const CACHE_DURATION_MS = 24 * 60 * 60 * 1000; // 24 hours

class GreetingService {
    private cachedGreeting: CachedGreeting | null = null;

    /**
     * Initialize greeting cache from localStorage
     */
    init(): void {
        try {
            const cached = localStorage.getItem(GREETING_CACHE_KEY);
            if (cached) {
                const parsed: CachedGreeting = JSON.parse(cached);
                // Check if cache is still valid (not expired)
                const age = Date.now() - parsed.timestamp;
                if (age < CACHE_DURATION_MS) {
                    this.cachedGreeting = parsed;
                    console.log('GreetingService: Loaded cached greeting from localStorage');
                } else {
                    console.log('GreetingService: Cached greeting expired, will regenerate');
                    localStorage.removeItem(GREETING_CACHE_KEY);
                }
            }
        } catch (error) {
            console.error('GreetingService: Error loading cache:', error);
        }
    }

    /**
     * Get cached greeting if available
     */
    getCachedGreeting(): CachedGreeting | null {
        return this.cachedGreeting;
    }

    /**
     * Cache a greeting for future use
     */
    cacheGreeting(text: string, audioBase64: string, userName?: string): void {
        const greeting: CachedGreeting = {
            text,
            audioBase64,
            timestamp: Date.now(),
            userName
        };
        
        this.cachedGreeting = greeting;
        
        try {
            localStorage.setItem(GREETING_CACHE_KEY, JSON.stringify(greeting));
            console.log('GreetingService: Cached greeting in localStorage');
        } catch (error) {
            console.error('GreetingService: Error caching greeting:', error);
            // localStorage might be full, but we still have it in memory
        }
    }

    /**
     * Check if cached greeting matches current user
     */
    isCachedForUser(userName?: string): boolean {
        if (!this.cachedGreeting) return false;
        return this.cachedGreeting.userName === userName;
    }

    /**
     * Clear cached greeting
     */
    clearCache(): void {
        this.cachedGreeting = null;
        try {
            localStorage.removeItem(GREETING_CACHE_KEY);
        } catch (error) {
            console.error('GreetingService: Error clearing cache:', error);
        }
    }
}

export const greetingService = new GreetingService();

