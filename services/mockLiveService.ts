import { LiveConnectionState } from '../types';

// This mimics the structure of a real Google GenAI Live Client
// It allows us to build the UI now and swap this file for real logic later.

type LiveConfig = {
    model: string;
    systemInstruction?: string;
};

export class MockLiveService {
    private connectionState: LiveConnectionState = LiveConnectionState.DISCONNECTED;
    private onStateChange: (state: LiveConnectionState) => void;
    private onAudioData: (base64Audio: string) => void;
    private onTextData: (text: string, isFinal: boolean) => void;
    
    // Simulation timers
    private responseTimer: ReturnType<typeof setTimeout> | null = null;

    constructor(
        onStateChange: (state: LiveConnectionState) => void,
        onAudioData: (base64Audio: string) => void,
        onTextData: (text: string, isFinal: boolean) => void
    ) {
        this.onStateChange = onStateChange;
        this.onAudioData = onAudioData;
        this.onTextData = onTextData;
    }

    public async connect(config: LiveConfig): Promise<void> {
        this.updateState(LiveConnectionState.CONNECTING);
        
        // Simulate network delay
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        this.updateState(LiveConnectionState.CONNECTED);
        console.log(`[MockService] Connected to ${config.model}`);
    }

    public async disconnect(): Promise<void> {
        if (this.responseTimer) clearTimeout(this.responseTimer);
        this.updateState(LiveConnectionState.DISCONNECTED);
        console.log('[MockService] Disconnected');
    }

    public sendAudioChunk(base64Audio: string): void {
        if (this.connectionState !== LiveConnectionState.CONNECTED) return;
        
        // No automatic response simulation.
        // Frontend only shows structure.
    }

    public sendText(text: string): void {
        if (this.connectionState !== LiveConnectionState.CONNECTED) return;
        
        console.log(`[MockService] User sent text: ${text}`);
        // No automatic response simulation.
    }

    private updateState(newState: LiveConnectionState) {
        this.connectionState = newState;
        this.onStateChange(newState);
    }
}