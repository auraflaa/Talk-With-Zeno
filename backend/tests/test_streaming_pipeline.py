"""
Test streaming pipeline with chunk-wise processing
Simulates the real frontend streaming behavior
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Tuple
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path, override=True)
else:
    load_dotenv('.env.local', override=True)

from backend.services.stt_service import get_stt_service
from backend.services.llm_service import get_llm_service
from backend.services.tts_service import get_tts_service
from backend.services.streaming_service import get_streaming_service


class StreamingPipelineTester:
    """Test streaming pipeline with chunk-wise processing"""
    
    def __init__(self):
        self.stt_service = get_stt_service()
        self.llm_service = get_llm_service()
        self.tts_service = get_tts_service()
        self.streaming_service = get_streaming_service()
        
        # Metrics tracking
        self.metrics = {
            'total_chunks': 0,
            'chunks_with_text': 0,
            'chunks_noise_only': 0,
            'stt_times': [],
            'llm_time': 0,
            'tts_time': 0,
            'total_time': 0,
            'chunk_sizes': [],
            'transcribed_texts': [],
            'merged_text': '',
            'final_response': '',
            'errors': []
        }
    
    def break_audio_into_chunks(self, audio_data: bytes, chunk_size_bytes: int = 15000) -> List[bytes]:
        """
        Break audio into chunks (simulating frontend behavior)
        Each chunk is ~2.5 seconds of audio (15KB for WebM/Opus at ~48kbps)
        """
        chunks = []
        for i in range(0, len(audio_data), chunk_size_bytes):
            chunk = audio_data[i:i + chunk_size_bytes]
            if len(chunk) >= 100:  # Minimum chunk size
                chunks.append(chunk)
        return chunks
    
    def process_chunk(self, chunk_data: bytes, session, audio_format: str = 'webm', 
                     language_code: str = 'en-US') -> Tuple[str, bool, bool]:
        """
        Process a single chunk through STT
        Returns: (transcribed_text, is_noise, has_text)
        """
        if not chunk_data or len(chunk_data) < 100:
            return ("", True, False)
        
        start_time = time.time()
        chunk_text = self.stt_service.transcribe_audio(
            chunk_data,
            language_code=language_code,
            audio_format=audio_format
        )
        stt_time = time.time() - start_time
        self.metrics['stt_times'].append(stt_time)
        
        is_noise = False
        has_text = False
        
        if not chunk_text or len(chunk_text.strip()) < 2:
            is_noise = True
            self.metrics['chunks_noise_only'] += 1
        else:
            chunk_text = chunk_text.strip()
            session.add_text_chunk(chunk_text)
            self.metrics['chunks_with_text'] += 1
            self.metrics['transcribed_texts'].append(chunk_text)
            has_text = True
        
        return (chunk_text or "", is_noise, has_text)
    
    def test_audio_file(self, audio_file_path: str) -> Dict:
        """
        Test an audio file through the streaming pipeline
        Simulates real frontend behavior: chunk-wise processing
        """
        print(f"\n{'='*80}")
        print(f"Testing: {Path(audio_file_path).name}")
        print(f"{'='*80}")
        
        if not os.path.exists(audio_file_path):
            return {
                'file': audio_file_path,
                'error': 'File not found',
                'success': False
            }
        
        # Reset metrics
        self.metrics = {
            'total_chunks': 0,
            'chunks_with_text': 0,
            'chunks_noise_only': 0,
            'stt_times': [],
            'llm_time': 0,
            'tts_time': 0,
            'total_time': 0,
            'chunk_sizes': [],
            'transcribed_texts': [],
            'merged_text': '',
            'final_response': '',
            'errors': []
        }
        
        start_total = time.time()
        
        try:
            # Read audio file
            with open(audio_file_path, 'rb') as f:
                audio_data = f.read()
            
            file_size = len(audio_data)
            print(f"File size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
            
            # Detect format
            audio_format = 'webm'
            if audio_file_path.endswith('.wav'):
                audio_format = 'wav'
            elif audio_file_path.endswith('.mp3'):
                audio_format = 'mp3'
            
            print(f"Audio format: {audio_format}")
            
            # Break into chunks (simulating frontend streaming)
            # Frontend sends chunks every 2.5 seconds
            # For WebM/Opus at ~48kbps: 2.5 seconds ≈ 15KB
            chunk_size_bytes = 15000  # ~2.5 seconds
            audio_chunks = self.break_audio_into_chunks(audio_data, chunk_size_bytes)
            
            self.metrics['total_chunks'] = len(audio_chunks)
            print(f"\nAudio broken into {len(audio_chunks)} chunks (chunk size: {chunk_size_bytes} bytes)")
            
            # Create streaming session
            user_id = 'test_user'
            conversation_id = 'test_conversation'
            session_id = self.streaming_service.create_session(user_id, conversation_id, 'en-US')
            session = self.streaming_service.get_session(session_id)
            
            if not session:
                return {
                    'file': audio_file_path,
                    'error': 'Failed to create streaming session',
                    'success': False
                }
            
            print(f"\nStreaming session created: {session_id}")
            print(f"\nProcessing chunks sequentially (simulating real pipeline)...")
            print("-" * 80)
            
            # Process chunks sequentially (as frontend does)
            chunks_processed = 0
            noise_detected_count = 0
            last_noise_chunk = -1
            
            for i, chunk_data in enumerate(audio_chunks):
                chunk_size = len(chunk_data)
                self.metrics['chunk_sizes'].append(chunk_size)
                
                # Add chunk to session
                session.add_chunk(chunk_data)
                
                # Process chunk with STT
                chunk_text, is_noise, has_text = self.process_chunk(
                    chunk_data, session, audio_format
                )
                
                chunks_processed += 1
                
                # Display chunk info
                status = "NOISE" if is_noise else "TEXT"
                print(f"Chunk {i+1}/{len(audio_chunks)}: {chunk_size:,} bytes | "
                      f"STT: {self.metrics['stt_times'][-1]*1000:.0f}ms | "
                      f"Status: {status}", end="")
                
                if has_text:
                    print(f" | Text: '{chunk_text[:50]}...'")
                else:
                    print()
                
                # Check if this is a noise chunk and we have accumulated text
                if is_noise:
                    noise_detected_count += 1
                    last_noise_chunk = i
                    
                    # Get merged text from all previous chunks
                    merged_text = session.get_merged_text()
                    
                    if merged_text and len(merged_text.strip()) >= 2:
                        # We have accumulated text - process with LLM
                        print(f"\n  → Noise detected! Merged text from {len(session.text_chunks)} chunks: '{merged_text}'")
                        print(f"  → Triggering LLM processing...")
                        
                        # Process with LLM
                        llm_start = time.time()
                        try:
                            from backend.services.storage_service import get_storage_service
                            storage_service = get_storage_service()
                            
                            conversation = storage_service.load_conversation(user_id, conversation_id)
                            conversation_history = conversation.get("messages", []) if conversation else []
                            
                            user_message = {
                                "role": "user",
                                "content": merged_text,
                                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S')
                            }
                            conversation_history.append(user_message)
                            
                            llm_result = self.llm_service.generate_response(
                                user_id=user_id,
                                user_message=merged_text,
                                conversation_history=conversation_history,
                                user_name='Test User'
                            )
                            
                            self.metrics['llm_time'] = time.time() - llm_start
                            self.metrics['merged_text'] = merged_text
                            self.metrics['final_response'] = llm_result.get('response', '')
                            
                            print(f"  → LLM response ({self.metrics['llm_time']*1000:.0f}ms): '{self.metrics['final_response'][:100]}...'")
                            
                            # Generate TTS
                            if self.metrics['final_response']:
                                tts_start = time.time()
                                try:
                                    tts_audio = self.tts_service.synthesize_speech(text=self.metrics['final_response'])
                                    self.metrics['tts_time'] = time.time() - tts_start
                                    if tts_audio:
                                        print(f"  → TTS generated ({self.metrics['tts_time']*1000:.0f}ms): {len(tts_audio):,} bytes")
                                    else:
                                        print(f"  → TTS failed")
                                except Exception as e:
                                    print(f"  → TTS error: {e}")
                                    self.metrics['errors'].append(f"TTS: {str(e)}")
                            
                            # Clear processed chunks
                            session.clear_text_chunks()
                            
                            # Break after processing (simulating real behavior)
                            break
                            
                        except Exception as e:
                            print(f"  → LLM error: {e}")
                            self.metrics['errors'].append(f"LLM: {str(e)}")
                            import traceback
                            traceback.print_exc()
            
            # If no noise was detected, process final merged text
            if not self.metrics['merged_text']:
                merged_text = session.get_merged_text()
                if merged_text and len(merged_text.strip()) >= 2:
                    print(f"\n  → No noise detected, processing final merged text: '{merged_text}'")
                    self.metrics['merged_text'] = merged_text
                    
                    llm_start = time.time()
                    try:
                        from backend.services.storage_service import get_storage_service
                        storage_service = get_storage_service()
                        
                        conversation = storage_service.load_conversation(user_id, conversation_id)
                        conversation_history = conversation.get("messages", []) if conversation else []
                        
                        user_message = {
                            "role": "user",
                            "content": merged_text,
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S')
                        }
                        conversation_history.append(user_message)
                        
                        llm_result = self.llm_service.generate_response(
                            user_id=user_id,
                            user_message=merged_text,
                            conversation_history=conversation_history,
                            user_name='Test User'
                        )
                        
                        self.metrics['llm_time'] = time.time() - llm_start
                        self.metrics['final_response'] = llm_result.get('response', '')
                        
                        # Generate TTS
                        if self.metrics['final_response']:
                            tts_start = time.time()
                            try:
                                tts_audio = self.tts_service.synthesize_speech(text=self.metrics['final_response'])
                                self.metrics['tts_time'] = time.time() - tts_start
                            except Exception as e:
                                self.metrics['errors'].append(f"TTS: {str(e)}")
                    except Exception as e:
                        self.metrics['errors'].append(f"LLM: {str(e)}")
            
            self.metrics['total_time'] = time.time() - start_total
            
            # Calculate statistics
            avg_stt_time = sum(self.metrics['stt_times']) / len(self.metrics['stt_times']) if self.metrics['stt_times'] else 0
            total_stt_time = sum(self.metrics['stt_times'])
            avg_chunk_size = sum(self.metrics['chunk_sizes']) / len(self.metrics['chunk_sizes']) if self.metrics['chunk_sizes'] else 0
            
            # Print performance matrix
            print(f"\n{'='*80}")
            print("PERFORMANCE MATRIX")
            print(f"{'='*80}")
            print(f"File: {Path(audio_file_path).name}")
            print(f"Size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
            print(f"Format: {audio_format}")
            print(f"\nChunk Analysis:")
            print(f"  Total chunks created: {self.metrics['total_chunks']}")
            print(f"  Chunks with text: {self.metrics['chunks_with_text']}")
            print(f"  Noise-only chunks: {self.metrics['chunks_noise_only']}")
            print(f"  Average chunk size: {avg_chunk_size:,.0f} bytes")
            print(f"  Chunk size range: {min(self.metrics['chunk_sizes']):,} - {max(self.metrics['chunk_sizes']):,} bytes")
            print(f"\nTiming Analysis:")
            print(f"  Total STT time: {total_stt_time*1000:.0f}ms ({len(self.metrics['stt_times'])} chunks)")
            print(f"  Average STT time per chunk: {avg_stt_time*1000:.0f}ms")
            print(f"  LLM time: {self.metrics['llm_time']*1000:.0f}ms")
            print(f"  TTS time: {self.metrics['tts_time']*1000:.0f}ms")
            print(f"  Total pipeline time: {self.metrics['total_time']*1000:.0f}ms")
            print(f"\nTranscription:")
            print(f"  Merged text: '{self.metrics['merged_text']}'")
            print(f"  Individual chunk texts: {len(self.metrics['transcribed_texts'])} chunks")
            if self.metrics['transcribed_texts']:
                for i, text in enumerate(self.metrics['transcribed_texts'], 1):
                    print(f"    Chunk {i}: '{text}'")
            print(f"\nResponse:")
            if self.metrics['final_response']:
                print(f"  LLM response: '{self.metrics['final_response'][:200]}...'")
                print(f"  Response length: {len(self.metrics['final_response'])} characters")
            else:
                print(f"  No LLM response generated")
            
            if self.metrics['errors']:
                print(f"\nErrors:")
                for error in self.metrics['errors']:
                    print(f"  - {error}")
            
            print(f"{'='*80}\n")
            
            return {
                'file': audio_file_path,
                'success': True,
                'metrics': self.metrics.copy(),
                'file_size': file_size,
                'format': audio_format,
                'total_chunks': self.metrics['total_chunks'],
                'chunks_with_text': self.metrics['chunks_with_text'],
                'chunks_noise_only': self.metrics['chunks_noise_only'],
                'avg_chunk_size': avg_chunk_size,
                'total_stt_time': total_stt_time,
                'avg_stt_time': avg_stt_time,
                'llm_time': self.metrics['llm_time'],
                'tts_time': self.metrics['tts_time'],
                'total_time': self.metrics['total_time'],
                'merged_text': self.metrics['merged_text'],
                'final_response': self.metrics['final_response'],
                'errors': self.metrics['errors']
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'file': audio_file_path,
                'error': str(e),
                'success': False,
                'traceback': traceback.format_exc()
            }


def main():
    """Test all audio files in demo_audio folder"""
    demo_audio_dir = Path(__file__).parent.parent / 'demo_audio'
    
    if not demo_audio_dir.exists():
        print(f"ERROR: Demo audio directory not found: {demo_audio_dir}")
        return
    
    # Find all audio files
    audio_extensions = ['.webm', '.wav', '.mp3', '.ogg', '.opus']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(demo_audio_dir.glob(f'*{ext}'))
        audio_files.extend(demo_audio_dir.glob(f'*{ext.upper()}'))
    
    if not audio_files:
        print(f"No audio files found in {demo_audio_dir}")
        print("Please add audio files (.webm, .wav, .mp3) to the demo_audio folder")
        return
    
    print(f"Found {len(audio_files)} audio file(s) to test")
    
    # Initialize tester
    tester = StreamingPipelineTester()
    
    # Test each file
    results = []
    for audio_file in sorted(audio_files):
        result = tester.test_audio_file(str(audio_file))
        results.append(result)
    
    # Summary report
    print(f"\n{'='*80}")
    print("SUMMARY REPORT")
    print(f"{'='*80}")
    
    successful = [r for r in results if r.get('success', False)]
    failed = [r for r in results if not r.get('success', False)]
    
    print(f"\nTotal files tested: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        print(f"\n{'='*80}")
        print("SUCCESSFUL TESTS - PERFORMANCE SUMMARY")
        print(f"{'='*80}")
        
        # Calculate averages
        avg_chunks = sum(r['total_chunks'] for r in successful) / len(successful)
        avg_stt_time = sum(r['avg_stt_time'] for r in successful) / len(successful)
        avg_llm_time = sum(r['llm_time'] for r in successful) / len(successful)
        avg_tts_time = sum(r['tts_time'] for r in successful) / len(successful)
        avg_total_time = sum(r['total_time'] for r in successful) / len(successful)
        
        print(f"\nAverage Metrics Across All Files:")
        print(f"  Average chunks per file: {avg_chunks:.1f}")
        print(f"  Average STT time per chunk: {avg_stt_time*1000:.0f}ms")
        print(f"  Average LLM time: {avg_llm_time*1000:.0f}ms")
        print(f"  Average TTS time: {avg_tts_time*1000:.0f}ms")
        print(f"  Average total pipeline time: {avg_total_time*1000:.0f}ms")
        
        print(f"\n{'='*80}")
        print("DETAILED RESULTS")
        print(f"{'='*80}")
        
        for result in successful:
            print(f"\n{Path(result['file']).name}:")
            print(f"  Chunks: {result['total_chunks']} (text: {result['chunks_with_text']}, noise: {result['chunks_noise_only']})")
            print(f"  STT: {result['total_stt_time']*1000:.0f}ms total, {result['avg_stt_time']*1000:.0f}ms avg/chunk")
            print(f"  LLM: {result['llm_time']*1000:.0f}ms")
            print(f"  TTS: {result['tts_time']*1000:.0f}ms")
            print(f"  Total: {result['total_time']*1000:.0f}ms")
            print(f"  Merged text: '{result['merged_text'][:80]}...'")
    
    if failed:
        print(f"\n{'='*80}")
        print("FAILED TESTS")
        print(f"{'='*80}")
        for result in failed:
            print(f"\n{Path(result['file']).name}:")
            print(f"  Error: {result.get('error', 'Unknown error')}")
    
    # Save results to JSON in performance_results folder
    performance_results_dir = Path(__file__).parent.parent / 'performance_results'
    performance_results_dir.mkdir(exist_ok=True)
    
    # Create timestamped filename
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = performance_results_dir / f'test_results_{timestamp}.json'
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    # Also save as latest (overwrite)
    latest_results_file = performance_results_dir / 'test_results.json'
    with open(latest_results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n\nResults saved to:")
    print(f"  - Latest: {latest_results_file}")
    print(f"  - Timestamped: {results_file}")


if __name__ == '__main__':
    main()

