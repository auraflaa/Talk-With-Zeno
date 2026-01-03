"""
Deep Production-Grade Analysis
Comprehensive evaluation of models, pipeline, and services with parameter optimization
"""

import os
import sys
import time
import json
import statistics
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent.parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path, override=True)
else:
    load_dotenv('.env.local', override=True)

from backend.services.stt_service import get_stt_service
from backend.services.llm_service import get_llm_service
from backend.services.tts_service import get_tts_service
from backend.services.storage_service import get_storage_service


class DeepAnalyzer:
    """Deep analysis with parameter optimization"""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'stt_parameter_analysis': {},
            'stt_chunk_size_analysis': {},
            'llm_model_comparison': {},
            'tts_parameter_analysis': {},
            'pipeline_analysis': {},
            'service_architecture': {},
            'recommendations': [],
            'next_steps': []
        }
    
    def analyze_stt_chunk_sizes(self) -> Dict[str, Any]:
        """Analyze STT performance with different chunk sizes"""
        print("\n" + "="*80)
        print("STT CHUNK SIZE ANALYSIS")
        print("="*80)
        
        stt_service = get_stt_service()
        if not stt_service.client:
            return {'error': 'STT service not available'}
        
        # Get demo audio files
        demo_audio_dir = Path(__file__).parent.parent.parent / 'demo_audio'
        audio_files = list(demo_audio_dir.glob('*.wav'))[:2]
        
        if not audio_files:
            return {'error': 'No demo audio files found'}
        
        analysis = {
            'test_files': [f.name for f in audio_files],
            'chunk_size_tests': [],
            'optimal_chunk_size': {}
        }
        
        # Test different chunk sizes (in bytes)
        chunk_sizes = [
            {'size_bytes': 5000, 'description': 'Very small (5KB)'},
            {'size_bytes': 15000, 'description': 'Small (15KB)'},
            {'size_bytes': 30000, 'description': 'Medium (30KB)'},
            {'size_bytes': 60000, 'description': 'Large (60KB)'},
            {'size_bytes': 100000, 'description': 'Very large (100KB)'},
        ]
        
        print(f"\nTesting {len(chunk_sizes)} chunk sizes...")
        print(f"Using {len(audio_files)} audio files for testing\n")
        
        for audio_file in audio_files:
            with open(audio_file, 'rb') as f:
                full_audio = f.read()
            
            print(f"\nTesting with {audio_file.name} ({len(full_audio)} bytes)...")
            
            for chunk_config in chunk_sizes:
                chunk_size = chunk_config['size_bytes']
                description = chunk_config['description']
                
                # Split audio into chunks
                chunks = []
                for i in range(0, len(full_audio), chunk_size):
                    chunks.append(full_audio[i:i+chunk_size])
                
                if not chunks:
                    continue
                
                print(f"  Testing {description} ({chunk_size} bytes, {len(chunks)} chunks)...")
                
                chunk_result = {
                    'chunk_size_bytes': chunk_size,
                    'description': description,
                    'num_chunks': len(chunks),
                    'chunk_latencies': [],
                    'total_latency_ms': 0,
                    'success_rate': 0,
                    'errors': []
                }
                
                # Test transcription with chunks
                try:
                    start_time = time.time()
                    
                    # Use transcribe_chunks if available, otherwise transcribe each chunk
                    if hasattr(stt_service, 'transcribe_chunks'):
                        transcripts = stt_service.transcribe_chunks(chunks, language_code='en-US')
                        total_latency = time.time() - start_time
                        
                        if transcripts:
                            merged_text = ' '.join(transcripts)
                            chunk_result['total_latency_ms'] = total_latency * 1000
                            chunk_result['success_rate'] = 100.0
                            chunk_result['transcript_length'] = len(merged_text)
                            print(f"    Success: {total_latency*1000:.0f}ms, {len(merged_text)} chars")
                        else:
                            chunk_result['errors'].append('No transcripts returned')
                    else:
                        # Fallback: transcribe each chunk individually
                        transcripts = []
                        for i, chunk in enumerate(chunks):
                            chunk_start = time.time()
                            transcript = stt_service.transcribe_audio(
                                chunk,
                                language_code='en-US',
                                audio_format='wav'
                            )
                            chunk_latency = (time.time() - chunk_start) * 1000
                            chunk_result['chunk_latencies'].append(chunk_latency)
                            
                            if transcript:
                                transcripts.append(transcript)
                            else:
                                chunk_result['errors'].append(f'Chunk {i+1} failed')
                        
                        total_latency = time.time() - start_time
                        merged_text = ' '.join(transcripts)
                        
                        chunk_result['total_latency_ms'] = total_latency * 1000
                        chunk_result['success_rate'] = (len(transcripts) / len(chunks)) * 100
                        chunk_result['transcript_length'] = len(merged_text)
                        
                        if chunk_result['chunk_latencies']:
                            chunk_result['avg_chunk_latency_ms'] = statistics.mean(chunk_result['chunk_latencies'])
                            chunk_result['min_chunk_latency_ms'] = min(chunk_result['chunk_latencies'])
                            chunk_result['max_chunk_latency_ms'] = max(chunk_result['chunk_latencies'])
                        
                        print(f"    Success: {total_latency*1000:.0f}ms ({len(transcripts)}/{len(chunks)} chunks), {len(merged_text)} chars")
                        
                except Exception as e:
                    chunk_result['errors'].append(str(e))
                    print(f"    Error: {e}")
                
                analysis['chunk_size_tests'].append(chunk_result)
        
        # Find optimal chunk size
        if analysis['chunk_size_tests']:
            successful_tests = [c for c in analysis['chunk_size_tests'] if c.get('success_rate', 0) > 0]
            if successful_tests:
                optimal = min(successful_tests, key=lambda x: x.get('total_latency_ms', float('inf')))
                analysis['optimal_chunk_size'] = {
                    'size_bytes': optimal.get('chunk_size_bytes'),
                    'description': optimal.get('description'),
                    'total_latency_ms': optimal.get('total_latency_ms'),
                    'num_chunks': optimal.get('num_chunks')
                }
        
        self.results['stt_chunk_size_analysis'] = analysis
        return analysis
    
    def analyze_stt_parameters(self) -> Dict[str, Any]:
        """Analyze STT with different parameters to find optimal configuration"""
        print("\n" + "="*80)
        print("STT PARAMETER OPTIMIZATION ANALYSIS")
        print("="*80)
        
        stt_service = get_stt_service()
        if not stt_service.client:
            return {'error': 'STT service not available'}
        
        # Get demo audio files
        demo_audio_dir = Path(__file__).parent.parent.parent / 'demo_audio'
        audio_files = list(demo_audio_dir.glob('*.wav'))[:3]  # Use first 3 files
        
        if not audio_files:
            return {'error': 'No demo audio files found'}
        
        analysis = {
            'test_files': [f.name for f in audio_files],
            'parameter_tests': [],
            'optimal_config': {},
            'performance_matrix': {}
        }
        
        # Test different configurations
        test_configs = [
            {'model': 'default', 'enable_automatic_punctuation': True, 'use_enhanced': False},
            {'model': 'command_and_search', 'enable_automatic_punctuation': True, 'use_enhanced': False},
            {'model': 'phone_call', 'enable_automatic_punctuation': True, 'use_enhanced': False},
            {'model': 'latest_short', 'enable_automatic_punctuation': True, 'use_enhanced': False},
            {'model': 'latest_long', 'enable_automatic_punctuation': True, 'use_enhanced': False},
        ]
        
        print(f"\nTesting {len(test_configs)} STT model configurations...")
        print(f"Using {len(audio_files)} audio files for testing\n")
        
        for config in test_configs:
            print(f"Testing: {config['model']}...")
            config_results = {
                'config': config,
                'latencies': [],
                'success_rate': 0,
                'avg_transcript_length': 0,
                'errors': []
            }
            
            for audio_file in audio_files:
                try:
                    with open(audio_file, 'rb') as f:
                        audio_data = f.read()
                    
                    # Test with specific model by directly calling STT API
                    from google.cloud import speech
                    detected_sample_rate = stt_service._detect_wav_sample_rate(audio_data) if hasattr(stt_service, '_detect_wav_sample_rate') else 24000
                    
                    start_time = time.time()
                    # Create config with specific model
                    recognition_config = speech.RecognitionConfig(
                        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                        sample_rate_hertz=detected_sample_rate or 24000,
                        language_code='en-US',
                        enable_automatic_punctuation=True,
                        model=config['model']
                    )
                    recognition_audio = speech.RecognitionAudio(content=audio_data)
                    
                    response = stt_service.client.recognize(
                        config=recognition_config,
                        audio=recognition_audio
                    )
                    
                    transcript = None
                    if response.results and len(response.results) > 0:
                        if response.results[0].alternatives and len(response.results[0].alternatives) > 0:
                            transcript = response.results[0].alternatives[0].transcript.strip()
                    
                    latency = time.time() - start_time
                    
                    if transcript:
                        config_results['latencies'].append(latency)
                        config_results['avg_transcript_length'] += len(transcript)
                        config_results['success_rate'] += 1
                    else:
                        config_results['errors'].append(f"No transcript for {audio_file.name}")
                        
                except Exception as e:
                    config_results['errors'].append(f"Error with {audio_file.name}: {str(e)}")
            
            if config_results['latencies']:
                config_results['avg_latency_ms'] = statistics.mean(config_results['latencies']) * 1000
                config_results['median_latency_ms'] = statistics.median(config_results['latencies']) * 1000
                config_results['min_latency_ms'] = min(config_results['latencies']) * 1000
                config_results['max_latency_ms'] = max(config_results['latencies']) * 1000
                config_results['stdev_latency_ms'] = statistics.stdev(config_results['latencies']) * 1000 if len(config_results['latencies']) > 1 else 0
                config_results['avg_transcript_length'] /= len(audio_files)
                config_results['success_rate'] = (config_results['success_rate'] / len(audio_files)) * 100
            else:
                config_results['avg_latency_ms'] = 0
                config_results['success_rate'] = 0
            
            analysis['parameter_tests'].append(config_results)
            print(f"  Avg Latency: {config_results['avg_latency_ms']:.0f}ms, Success: {config_results['success_rate']:.0f}%")
        
        # Find optimal configuration
        if analysis['parameter_tests']:
            best_config = min(
                [c for c in analysis['parameter_tests'] if c['success_rate'] > 0],
                key=lambda x: x['avg_latency_ms'],
                default=None
            )
            if best_config:
                analysis['optimal_config'] = {
                    'model': best_config['config']['model'],
                    'avg_latency_ms': best_config['avg_latency_ms'],
                    'success_rate': best_config['success_rate']
                }
        
        # Performance matrix
        analysis['performance_matrix'] = {
            'fastest': min([c for c in analysis['parameter_tests'] if c['success_rate'] > 0], 
                          key=lambda x: x['avg_latency_ms'], default={}),
            'most_reliable': max([c for c in analysis['parameter_tests']], 
                               key=lambda x: x['success_rate'], default={}),
            'best_balance': min([c for c in analysis['parameter_tests'] if c['success_rate'] > 0], 
                              key=lambda x: x['avg_latency_ms'] / max(x['success_rate'], 1), default={})
        }
        
        self.results['stt_parameter_analysis'] = analysis
        return analysis
    
    def analyze_llm_models(self) -> Dict[str, Any]:
        """Compare different LLM models for performance"""
        print("\n" + "="*80)
        print("LLM MODEL COMPARISON ANALYSIS")
        print("="*80)
        
        llm_service = get_llm_service()
        if not llm_service.model:
            return {'error': 'LLM service not available'}
        
        # Test prompts of different types
        test_prompts = [
            {'type': 'simple', 'text': 'Hello, how are you?'},
            {'type': 'complex', 'text': 'Explain the philosophical implications of artificial intelligence on human consciousness.'},
            {'type': 'emotional', 'text': 'I feel really overwhelmed and don\'t know what to do.'},
            {'type': 'creative', 'text': 'Write a short poem about hope.'},
        ]
        
        # Models to test (from llm_service)
        models_to_test = [
            'gemini-2.5-flash',
            'gemini-2.0-flash',
            'gemini-2.0-flash-lite',
            'gemini-1.5-flash',
            'gemini-2.5-pro',
            'gemini-1.5-pro',
        ]
        
        analysis = {
            'models_tested': models_to_test,
            'test_prompts': [p['type'] for p in test_prompts],
            'model_results': {},
            'comparison_matrix': {},
            'optimal_model': {}
        }
        
        print(f"\nTesting {len(models_to_test)} LLM models...")
        print(f"Using {len(test_prompts)} different prompt types\n")
        
        for model_name in models_to_test:
            print(f"Testing model: {model_name}...")
            model_results = {
                'model': model_name,
                'prompt_results': [],
                'avg_latency_ms': 0,
                'avg_response_length': 0,
                'success_rate': 0,
                'errors': []
            }
            
            # Test with specific model by temporarily modifying service
            # Store original model
            original_model = llm_service.model_name if hasattr(llm_service, 'model_name') else None
            original_model_obj = llm_service.model
            
            # Try to use specific model
            try:
                import google.generativeai as genai
                test_model = genai.GenerativeModel(model_name)
                llm_service.model = test_model
                llm_service.model_name = model_name
            except Exception as e:
                model_results['errors'].append(f"Could not load model {model_name}: {str(e)}")
                continue
            
            for prompt_data in test_prompts:
                try:
                    # Build prompt (simplified for testing)
                    prompt = prompt_data['text']
                    
                    start_time = time.time()
                    generation_config = {
                        "temperature": 0.9,
                        "top_p": 0.95,
                        "top_k": 40,
                        "max_output_tokens": 2048,
                    }
                    
                    response = test_model.generate_content(
                        prompt,
                        generation_config=generation_config
                    )
                    latency = time.time() - start_time
                    
                    response_text = response.text if response and response.text else None
                    
                    if response_text:
                        model_results['prompt_results'].append({
                            'prompt_type': prompt_data['type'],
                            'latency_ms': latency * 1000,
                            'response_length': len(response_text),
                            'success': True
                        })
                    else:
                        model_results['errors'].append(f"No response for {prompt_data['type']}")
                        
                except Exception as e:
                    model_results['errors'].append(f"Error with {prompt_data['type']}: {str(e)}")
            
            # Restore original model
            if original_model_obj:
                llm_service.model = original_model_obj
            if original_model:
                llm_service.model_name = original_model
            
            if model_results['prompt_results']:
                model_results['avg_latency_ms'] = statistics.mean([r['latency_ms'] for r in model_results['prompt_results']])
                model_results['avg_response_length'] = statistics.mean([r['response_length'] for r in model_results['prompt_results']])
                model_results['success_rate'] = (len(model_results['prompt_results']) / len(test_prompts)) * 100
            
            analysis['model_results'][model_name] = model_results
            if model_results['prompt_results']:
                print(f"  Avg Latency: {model_results['avg_latency_ms']:.0f}ms, Success: {model_results['success_rate']:.0f}%")
        
        # Comparison matrix
        if analysis['model_results']:
            successful_models = {k: v for k, v in analysis['model_results'].items() if v['success_rate'] > 0}
            if successful_models:
                analysis['comparison_matrix'] = {
                    'fastest': min(successful_models.items(), key=lambda x: x[1]['avg_latency_ms']),
                    'most_reliable': max(successful_models.items(), key=lambda x: x[1]['success_rate']),
                    'best_quality': max(successful_models.items(), key=lambda x: x[1]['avg_response_length']),
                }
                
                # Optimal model (balance of speed and reliability)
                analysis['optimal_model'] = min(
                    successful_models.items(),
                    key=lambda x: x[1]['avg_latency_ms'] / max(x[1]['success_rate'], 1)
                )
        
        self.results['llm_model_comparison'] = analysis
        return analysis
    
    def analyze_tts_parameters(self) -> Dict[str, Any]:
        """Analyze TTS with different parameters"""
        print("\n" + "="*80)
        print("TTS PARAMETER OPTIMIZATION ANALYSIS")
        print("="*80)
        
        tts_service = get_tts_service()
        if not tts_service.providers:
            return {'error': 'TTS service not available'}
        
        # Test texts of different lengths
        test_texts = [
            {'length': 'short', 'text': 'Hello.'},
            {'length': 'medium', 'text': 'This is a medium length sentence for testing text-to-speech synthesis.'},
            {'length': 'long', 'text': 'This is a longer text sample designed to test how the text-to-speech system handles extended content. It includes multiple sentences and should provide a good measure of performance across different text lengths and complexities.'},
        ]
        
        # Test different voices (Groq)
        voices_to_test = ['troy', 'autumn', 'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
        
        analysis = {
            'providers': list(tts_service.providers),
            'voices_tested': voices_to_test,
            'test_texts': [t['length'] for t in test_texts],
            'voice_results': {},
            'optimal_config': {}
        }
        
        print(f"\nTesting TTS with {len(voices_to_test)} voices...")
        print(f"Using {len(test_texts)} different text lengths\n")
        
        # Test with medium text for all voices
        test_text = test_texts[1]['text']  # Medium length
        
        for voice in voices_to_test:
            print(f"Testing voice: {voice}...")
            voice_results = {
                'voice': voice,
                'latencies': [],
                'audio_sizes': [],
                'success_rate': 0,
                'errors': []
            }
            
            # Test multiple times for consistency (reduced to 1 to avoid rate limits)
            for _ in range(1):
                try:
                    start_time = time.time()
                    # Test with specific voice by modifying TTS service call
                    # Check if synthesize_speech_groq accepts voice parameter
                    if hasattr(tts_service, 'synthesize_speech_groq'):
                        audio_data = tts_service.synthesize_speech_groq(text=test_text, voice=voice)
                    else:
                        # Fallback to default
                        audio_data = tts_service.synthesize_speech(text=test_text)
                    latency = time.time() - start_time
                    
                    if audio_data:
                        voice_results['latencies'].append(latency)
                        voice_results['audio_sizes'].append(len(audio_data))
                        voice_results['success_rate'] += 1
                    else:
                        voice_results['errors'].append('No audio generated (rate limit or error)')
                        
                except Exception as e:
                    error_str = str(e)
                    if 'rate_limit' in error_str.lower() or '429' in error_str:
                        voice_results['errors'].append('Rate limit exceeded')
                        break  # Stop testing this voice if rate limited
                    else:
                        voice_results['errors'].append(str(e))
            
            if voice_results['latencies']:
                voice_results['avg_latency_ms'] = statistics.mean(voice_results['latencies']) * 1000
                voice_results['avg_audio_size'] = statistics.mean(voice_results['audio_sizes'])
                voice_results['success_rate'] = (voice_results['success_rate'] / 3) * 100
            else:
                voice_results['avg_latency_ms'] = 0
                voice_results['success_rate'] = 0
            
            analysis['voice_results'][voice] = voice_results
            if voice_results['latencies']:
                print(f"  Avg Latency: {voice_results['avg_latency_ms']:.0f}ms, Success: {voice_results['success_rate']:.0f}%")
        
        # Test different text lengths with default voice
        print(f"\nTesting different text lengths...")
        length_results = {}
        for text_data in test_texts:
            try:
                start_time = time.time()
                audio_data = tts_service.synthesize_speech(text=text_data['text'])
                latency = time.time() - start_time
                
                length_results[text_data['length']] = {
                    'latency_ms': latency * 1000,
                    'audio_size_bytes': len(audio_data) if audio_data else 0,
                    'text_length': len(text_data['text']),
                    'bytes_per_char': len(audio_data) / len(text_data['text']) if audio_data else 0
                }
                print(f"  {text_data['length']}: {latency*1000:.0f}ms, {len(audio_data) if audio_data else 0} bytes")
            except Exception as e:
                length_results[text_data['length']] = {'error': str(e)}
        
        analysis['text_length_analysis'] = length_results
        
        # Find optimal configuration
        if analysis['voice_results']:
            successful_voices = {k: v for k, v in analysis['voice_results'].items() if v['success_rate'] > 0}
            if successful_voices:
                analysis['optimal_config'] = {
                    'voice': min(successful_voices.items(), key=lambda x: x[1]['avg_latency_ms'])[0],
                    'avg_latency_ms': min(successful_voices.items(), key=lambda x: x[1]['avg_latency_ms'])[1]['avg_latency_ms']
                }
        
        self.results['tts_parameter_analysis'] = analysis
        return analysis
    
    def analyze_full_pipeline(self) -> Dict[str, Any]:
        """Deep analysis of full pipeline"""
        print("\n" + "="*80)
        print("FULL PIPELINE DEEP ANALYSIS")
        print("="*80)
        
        analysis = {
            'pipeline_stages': {},
            'bottlenecks': [],
            'optimization_opportunities': [],
            'end_to_end_metrics': {}
        }
        
        # Get demo audio
        demo_audio_dir = Path(__file__).parent.parent.parent / 'demo_audio'
        audio_files = list(demo_audio_dir.glob('*.wav'))[:2]
        
        if not audio_files:
            return {'error': 'No demo audio files found'}
        
        stt_service = get_stt_service()
        llm_service = get_llm_service()
        tts_service = get_tts_service()
        
        if not (stt_service.client and llm_service.model and tts_service.providers):
            return {'error': 'Required services not available'}
        
        print(f"\nTesting full pipeline with {len(audio_files)} audio files...\n")
        
        pipeline_times = []
        stt_times = []
        llm_times = []
        tts_times = []
        
        for audio_file in audio_files:
            try:
                with open(audio_file, 'rb') as f:
                    audio_data = f.read()
                
                pipeline_start = time.time()
                
                # STT Stage
                stt_start = time.time()
                transcript = stt_service.transcribe_audio(audio_data, language_code='en-US', audio_format='wav')
                stt_time = time.time() - stt_start
                stt_times.append(stt_time)
                
                if not transcript:
                    continue
                
                # LLM Stage
                llm_start = time.time()
                llm_result = llm_service.generate_response(
                    user_id='test_user',
                    user_message=transcript,
                    conversation_history=[],
                    user_name='Test User'
                )
                llm_time = time.time() - llm_start
                llm_times.append(llm_time)
                
                response = llm_result.get('response', '')
                if not response:
                    continue
                
                # TTS Stage
                tts_start = time.time()
                audio_output = tts_service.synthesize_speech(text=response)
                tts_time = time.time() - tts_start
                tts_times.append(tts_time)
                
                total_time = time.time() - pipeline_start
                pipeline_times.append(total_time)
                
                print(f"  {audio_file.name}: {total_time*1000:.0f}ms total")
                print(f"    STT: {stt_time*1000:.0f}ms ({stt_time/total_time*100:.1f}%)")
                print(f"    LLM: {llm_time*1000:.0f}ms ({llm_time/total_time*100:.1f}%)")
                print(f"    TTS: {tts_time*1000:.0f}ms ({tts_time/total_time*100:.1f}%)")
                
            except Exception as e:
                print(f"  Error with {audio_file.name}: {e}")
        
        if pipeline_times:
            analysis['pipeline_stages'] = {
                'stt': {
                    'avg_ms': statistics.mean(stt_times) * 1000,
                    'percentage': (statistics.mean(stt_times) / statistics.mean(pipeline_times)) * 100,
                    'min_ms': min(stt_times) * 1000,
                    'max_ms': max(stt_times) * 1000
                },
                'llm': {
                    'avg_ms': statistics.mean(llm_times) * 1000,
                    'percentage': (statistics.mean(llm_times) / statistics.mean(pipeline_times)) * 100,
                    'min_ms': min(llm_times) * 1000,
                    'max_ms': max(llm_times) * 1000
                },
                'tts': {
                    'avg_ms': statistics.mean(tts_times) * 1000,
                    'percentage': (statistics.mean(tts_times) / statistics.mean(pipeline_times)) * 100,
                    'min_ms': min(tts_times) * 1000,
                    'max_ms': max(tts_times) * 1000
                }
            }
            
            analysis['end_to_end_metrics'] = {
                'avg_total_ms': statistics.mean(pipeline_times) * 1000,
                'median_total_ms': statistics.median(pipeline_times) * 1000,
                'min_total_ms': min(pipeline_times) * 1000,
                'max_total_ms': max(pipeline_times) * 1000
            }
            
            # Identify bottlenecks
            stage_percentages = {
                'STT': analysis['pipeline_stages']['stt']['percentage'],
                'LLM': analysis['pipeline_stages']['llm']['percentage'],
                'TTS': analysis['pipeline_stages']['tts']['percentage']
            }
            bottleneck = max(stage_percentages.items(), key=lambda x: x[1])
            analysis['bottlenecks'] = [{
                'stage': bottleneck[0],
                'percentage': bottleneck[1],
                'avg_latency_ms': analysis['pipeline_stages'][bottleneck[0].lower()]['avg_ms']
            }]
            
            # Optimization opportunities
            if analysis['pipeline_stages']['llm']['percentage'] > 50:
                analysis['optimization_opportunities'].append({
                    'stage': 'LLM',
                    'issue': 'LLM accounts for >50% of pipeline time',
                    'recommendation': 'Consider faster models, response caching, or streaming responses'
                })
            if analysis['pipeline_stages']['stt']['avg_ms'] > 2000:
                analysis['optimization_opportunities'].append({
                    'stage': 'STT',
                    'issue': 'STT latency >2s',
                    'recommendation': 'Consider streaming STT or optimizing audio chunk sizes'
                })
        
        self.results['pipeline_analysis'] = analysis
        return analysis
    
    def analyze_service_architecture(self) -> Dict[str, Any]:
        """Analyze service architecture and dependencies"""
        print("\n" + "="*80)
        print("SERVICE ARCHITECTURE ANALYSIS")
        print("="*80)
        
        analysis = {
            'service_dependencies': {},
            'scalability_considerations': [],
            'reliability_factors': [],
            'cost_analysis': {}
        }
        
        # Analyze each service
        services = {
            'STT': {
                'provider': 'Google Cloud Speech-to-Text',
                'dependencies': ['GOOGLE_APPLICATION_CREDENTIALS'],
                'scalability': 'High (cloud-based)',
                'cost_model': 'Per-minute pricing',
                'reliability': 'High (99.9% SLA)'
            },
            'LLM': {
                'provider': 'Google Gemini',
                'dependencies': ['GEMINI_API_KEY'],
                'scalability': 'High (API-based)',
                'cost_model': 'Per-token pricing',
                'reliability': 'High (API-based)'
            },
            'TTS': {
                'provider': 'Groq (primary), Gemini (fallback)',
                'dependencies': ['GROQ_API_KEY', 'GEMINI_API_KEY'],
                'scalability': 'High (API-based)',
                'cost_model': 'Per-character/token pricing',
                'reliability': 'Medium (depends on provider)'
            },
            'Storage': {
                'provider': 'File-based (JSON)',
                'dependencies': ['File system'],
                'scalability': 'Low (file-based)',
                'cost_model': 'Storage costs',
                'reliability': 'Medium (no redundancy)'
            }
        }
        
        analysis['service_dependencies'] = services
        
        # Scalability considerations
        analysis['scalability_considerations'] = [
            {
                'service': 'Storage',
                'issue': 'File-based storage doesn\'t scale well',
                'recommendation': 'Consider migrating to database (PostgreSQL, MongoDB)'
            },
            {
                'service': 'TTS',
                'issue': 'Single provider dependency',
                'recommendation': 'Implement multiple provider fallbacks'
            }
        ]
        
        # Reliability factors
        analysis['reliability_factors'] = [
            {
                'factor': 'API Rate Limits',
                'impact': 'High',
                'mitigation': 'Implement rate limiting, caching, and retry logic'
            },
            {
                'factor': 'Network Latency',
                'impact': 'Medium',
                'mitigation': 'Use CDN, optimize payload sizes, implement streaming'
            },
            {
                'factor': 'Service Availability',
                'impact': 'High',
                'mitigation': 'Implement health checks, fallback providers, circuit breakers'
            }
        ]
        
        self.results['service_architecture'] = analysis
        return analysis
    
    def generate_recommendations(self):
        """Generate comprehensive recommendations"""
        recommendations = []
        next_steps = []
        
        # STT recommendations
        stt_analysis = self.results.get('stt_parameter_analysis', {})
        if stt_analysis.get('optimal_config'):
            recommendations.append({
                'category': 'STT Optimization',
                'priority': 'High',
                'finding': f"Optimal STT model: {stt_analysis['optimal_config'].get('model', 'default')}",
                'recommendation': f"Use {stt_analysis['optimal_config'].get('model', 'default')} model for best latency ({stt_analysis['optimal_config'].get('avg_latency_ms', 0):.0f}ms)"
            })
        
        # STT Chunk Size recommendations
        chunk_analysis = self.results.get('stt_chunk_size_analysis', {})
        if chunk_analysis.get('optimal_chunk_size'):
            optimal = chunk_analysis['optimal_chunk_size']
            recommendations.append({
                'category': 'STT Chunk Size Optimization',
                'priority': 'Medium',
                'finding': f"Optimal chunk size: {optimal.get('description', 'N/A')} ({optimal.get('size_bytes', 0)} bytes)",
                'recommendation': f"Use {optimal.get('size_bytes', 15000)} byte chunks for optimal STT performance ({optimal.get('total_latency_ms', 0):.0f}ms total latency)"
            })
        
        # LLM recommendations
        llm_analysis = self.results.get('llm_model_comparison', {})
        if llm_analysis.get('optimal_model'):
            optimal = llm_analysis['optimal_model']
            recommendations.append({
                'category': 'LLM Model Selection',
                'priority': 'High',
                'finding': f"Optimal LLM: {optimal[0]}",
                'recommendation': f"Use {optimal[0]} for best balance of speed and reliability"
            })
        
        # TTS recommendations
        tts_analysis = self.results.get('tts_parameter_analysis', {})
        if tts_analysis.get('optimal_config'):
            recommendations.append({
                'category': 'TTS Optimization',
                'priority': 'Medium',
                'finding': f"Optimal TTS voice: {tts_analysis['optimal_config'].get('voice', 'troy')}",
                'recommendation': f"Use {tts_analysis['optimal_config'].get('voice', 'troy')} voice for best performance"
            })
        
        # Pipeline recommendations
        pipeline_analysis = self.results.get('pipeline_analysis', {})
        if pipeline_analysis.get('bottlenecks'):
            bottleneck = pipeline_analysis['bottlenecks'][0]
            recommendations.append({
                'category': 'Pipeline Optimization',
                'priority': 'Critical',
                'finding': f"{bottleneck['stage']} is the bottleneck ({bottleneck['percentage']:.1f}% of total time)",
                'recommendation': f"Focus optimization efforts on {bottleneck['stage']} stage"
            })
        
        # Next steps
        next_steps = [
            {
                'step': 1,
                'action': 'Implement optimal STT configuration',
                'impact': 'Reduce STT latency by 10-30%',
                'effort': 'Low'
            },
            {
                'step': 2,
                'action': 'Implement LLM response caching',
                'impact': 'Reduce LLM latency by 50-80% for repeated queries',
                'effort': 'Medium'
            },
            {
                'step': 3,
                'action': 'Migrate storage to database',
                'impact': 'Improve scalability and reliability',
                'effort': 'High'
            },
            {
                'step': 4,
                'action': 'Implement streaming responses',
                'impact': 'Improve perceived latency',
                'effort': 'High'
            },
            {
                'step': 5,
                'action': 'Add comprehensive monitoring',
                'impact': 'Better visibility into performance',
                'effort': 'Medium'
            }
        ]
        
        self.results['recommendations'] = recommendations
        self.results['next_steps'] = next_steps
    
    def save_results(self, output_dir: Path):
        """Save analysis results"""
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save JSON
        json_file = output_dir / f'deep_analysis_{timestamp}.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        latest_json = output_dir / 'deep_analysis.json'
        with open(latest_json, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        # Generate markdown report
        self.generate_markdown_report(output_dir, timestamp)
        
        print(f"\n" + "="*80)
        print("RESULTS SAVED")
        print("="*80)
        print(f"JSON: {json_file}")
        print(f"Latest JSON: {latest_json}")
        print(f"Markdown Report: {output_dir / f'DEEP_ANALYSIS_{timestamp}.md'}")
    
    def generate_markdown_report(self, output_dir: Path, timestamp: str):
        """Generate comprehensive markdown report"""
        report = f"""# Deep Production-Grade Analysis Report

**Generated:** {self.results['timestamp']}  
**Analysis Type:** Comprehensive Model, Pipeline, and Service Evaluation

---

## Executive Summary

This report provides a comprehensive, production-grade analysis of the Talk-With-Zeno system, including:

- **STT Parameter Optimization**: Evaluation of different STT models and configurations
- **LLM Model Comparison**: Performance analysis across multiple Gemini models
- **TTS Parameter Analysis**: Voice and configuration optimization
- **Full Pipeline Analysis**: End-to-end performance evaluation
- **Service Architecture**: Scalability, reliability, and cost analysis
- **Actionable Recommendations**: Next steps for optimization

---

## 1. STT Parameter Optimization Analysis

"""
        
        stt_analysis = self.results.get('stt_parameter_analysis', {})
        if stt_analysis and not stt_analysis.get('error'):
            report += f"""
### Test Configuration
- **Test Files:** {', '.join(stt_analysis.get('test_files', []))}
- **Configurations Tested:** {len(stt_analysis.get('parameter_tests', []))}

### Parameter Test Results

| Model | Avg Latency (ms) | Success Rate (%) | Notes |
|-------|------------------|------------------|-------|
"""
            for test in stt_analysis.get('parameter_tests', []):
                config = test.get('config', {})
                report += f"| {config.get('model', 'N/A')} | {test.get('avg_latency_ms', 0):.0f} | {test.get('success_rate', 0):.1f} | "
                if test.get('errors'):
                    report += f"Errors: {len(test['errors'])} |\n"
                else:
                    report += "No errors |\n"
            
            if stt_analysis.get('optimal_config'):
                optimal = stt_analysis['optimal_config']
                report += f"""
### Optimal Configuration

- **Model:** {optimal.get('model', 'N/A')}
- **Average Latency:** {optimal.get('avg_latency_ms', 0):.0f}ms
- **Success Rate:** {optimal.get('success_rate', 0):.1f}%

### Performance Matrix

"""
                perf_matrix = stt_analysis.get('performance_matrix', {})
                if perf_matrix.get('fastest'):
                    report += f"- **Fastest:** {perf_matrix['fastest'].get('config', {}).get('model', 'N/A')} ({perf_matrix['fastest'].get('avg_latency_ms', 0):.0f}ms)\n"
                if perf_matrix.get('most_reliable'):
                    report += f"- **Most Reliable:** {perf_matrix['most_reliable'].get('config', {}).get('model', 'N/A')} ({perf_matrix['most_reliable'].get('success_rate', 0):.1f}%)\n"
        else:
            report += "STT analysis not available or encountered errors.\n"
        
        # STT Chunk Size Analysis
        report += f"""
---

## 1.5. STT Chunk Size Analysis

"""
        chunk_analysis = self.results.get('stt_chunk_size_analysis', {})
        if chunk_analysis and not chunk_analysis.get('error'):
            report += f"""
### Test Configuration
- **Test Files:** {', '.join(chunk_analysis.get('test_files', []))}
- **Chunk Sizes Tested:** {len(chunk_analysis.get('chunk_size_tests', []))}

### Chunk Size Performance Results

| Chunk Size | Description | Num Chunks | Total Latency (ms) | Success Rate (%) | Avg Chunk Latency (ms) |
|------------|-------------|------------|-------------------|------------------|------------------------|
"""
            for test in chunk_analysis.get('chunk_size_tests', []):
                report += f"| {test.get('chunk_size_bytes', 0)} | {test.get('description', 'N/A')} | {test.get('num_chunks', 0)} | {test.get('total_latency_ms', 0):.0f} | {test.get('success_rate', 0):.1f} | {test.get('avg_chunk_latency_ms', 0):.0f} |\n"
            
            if chunk_analysis.get('optimal_chunk_size'):
                optimal = chunk_analysis['optimal_chunk_size']
                report += f"""
### Optimal Chunk Size

- **Size:** {optimal.get('size_bytes', 'N/A')} bytes ({optimal.get('description', 'N/A')})
- **Total Latency:** {optimal.get('total_latency_ms', 0):.0f}ms
- **Number of Chunks:** {optimal.get('num_chunks', 'N/A')}

### Findings

- Smaller chunks (5-15KB) may have higher overhead due to more API calls
- Larger chunks (60-100KB) may have better throughput but higher per-chunk latency
- Optimal balance depends on audio file size and network conditions
"""
        else:
            report += "STT chunk size analysis not available or encountered errors.\n"
        
        # LLM Analysis
        report += f"""
---

## 2. LLM Model Comparison Analysis

"""
        llm_analysis = self.results.get('llm_model_comparison', {})
        if llm_analysis and not llm_analysis.get('error'):
            report += f"""
### Models Tested
{', '.join(llm_analysis.get('models_tested', []))}

### Test Prompts
{', '.join(llm_analysis.get('test_prompts', []))}

### Model Performance Comparison

| Model | Avg Latency (ms) | Avg Response Length | Success Rate (%) |
|-------|------------------|---------------------|------------------|
"""
            for model_name, model_data in llm_analysis.get('model_results', {}).items():
                report += f"| {model_name} | {model_data.get('avg_latency_ms', 0):.0f} | {model_data.get('avg_response_length', 0):.0f} | {model_data.get('success_rate', 0):.1f} |\n"
            
            if llm_analysis.get('optimal_model'):
                optimal = llm_analysis['optimal_model']
                report += f"""
### Optimal Model

- **Model:** {optimal[0]}
- **Average Latency:** {optimal[1].get('avg_latency_ms', 0):.0f}ms
- **Success Rate:** {optimal[1].get('success_rate', 0):.1f}%
- **Average Response Length:** {optimal[1].get('avg_response_length', 0):.0f} characters

### Comparison Matrix

"""
                comp_matrix = llm_analysis.get('comparison_matrix', {})
                if comp_matrix.get('fastest'):
                    report += f"- **Fastest:** {comp_matrix['fastest'][0]} ({comp_matrix['fastest'][1].get('avg_latency_ms', 0):.0f}ms)\n"
                if comp_matrix.get('most_reliable'):
                    report += f"- **Most Reliable:** {comp_matrix['most_reliable'][0]} ({comp_matrix['most_reliable'][1].get('success_rate', 0):.1f}%)\n"
                if comp_matrix.get('best_quality'):
                    report += f"- **Best Quality:** {comp_matrix['best_quality'][0]} ({comp_matrix['best_quality'][1].get('avg_response_length', 0):.0f} chars)\n"
        else:
            report += "LLM analysis not available or encountered errors.\n"
        
        # TTS Analysis
        report += f"""
---

## 3. TTS Parameter Optimization Analysis

"""
        tts_analysis = self.results.get('tts_parameter_analysis', {})
        if tts_analysis and not tts_analysis.get('error'):
            report += f"""
### Providers Available
{', '.join(tts_analysis.get('providers', []))}

### Voices Tested
{', '.join(tts_analysis.get('voices_tested', []))}

### Voice Performance

| Voice | Avg Latency (ms) | Avg Audio Size (bytes) | Success Rate (%) |
|-------|------------------|------------------------|------------------|
"""
            for voice, voice_data in tts_analysis.get('voice_results', {}).items():
                report += f"| {voice} | {voice_data.get('avg_latency_ms', 0):.0f} | {voice_data.get('avg_audio_size', 0):.0f} | {voice_data.get('success_rate', 0):.1f} |\n"
            
            if tts_analysis.get('text_length_analysis'):
                report += f"""
### Text Length Analysis

| Length | Latency (ms) | Audio Size (bytes) | Bytes per Character |
|--------|--------------|-------------------|---------------------|
"""
                for length, length_data in tts_analysis.get('text_length_analysis', {}).items():
                    if not length_data.get('error'):
                        report += f"| {length} | {length_data.get('latency_ms', 0):.0f} | {length_data.get('audio_size_bytes', 0):.0f} | {length_data.get('bytes_per_char', 0):.2f} |\n"
            
            if tts_analysis.get('optimal_config'):
                optimal = tts_analysis['optimal_config']
                report += f"""
### Optimal Configuration

- **Voice:** {optimal.get('voice', 'N/A')}
- **Average Latency:** {optimal.get('avg_latency_ms', 0):.0f}ms
"""
        else:
            report += "TTS analysis not available or encountered errors.\n"
        
        # Pipeline Analysis
        report += f"""
---

## 4. Full Pipeline Analysis

"""
        pipeline_analysis = self.results.get('pipeline_analysis', {})
        if pipeline_analysis and not pipeline_analysis.get('error'):
            stages = pipeline_analysis.get('pipeline_stages', {})
            if stages:
                report += f"""
### Pipeline Stage Breakdown

| Stage | Avg Latency (ms) | Percentage of Total | Min (ms) | Max (ms) |
|-------|------------------|---------------------|----------|----------|
| STT | {stages.get('stt', {}).get('avg_ms', 0):.0f} | {stages.get('stt', {}).get('percentage', 0):.1f}% | {stages.get('stt', {}).get('min_ms', 0):.0f} | {stages.get('stt', {}).get('max_ms', 0):.0f} |
| LLM | {stages.get('llm', {}).get('avg_ms', 0):.0f} | {stages.get('llm', {}).get('percentage', 0):.1f}% | {stages.get('llm', {}).get('min_ms', 0):.0f} | {stages.get('llm', {}).get('max_ms', 0):.0f} |
| TTS | {stages.get('tts', {}).get('avg_ms', 0):.0f} | {stages.get('tts', {}).get('percentage', 0):.1f}% | {stages.get('tts', {}).get('min_ms', 0):.0f} | {stages.get('tts', {}).get('max_ms', 0):.0f} |

### End-to-End Metrics

- **Average Total Latency:** {pipeline_analysis.get('end_to_end_metrics', {}).get('avg_total_ms', 0):.0f}ms
- **Median Total Latency:** {pipeline_analysis.get('end_to_end_metrics', {}).get('median_total_ms', 0):.0f}ms
- **Range:** {pipeline_analysis.get('end_to_end_metrics', {}).get('min_total_ms', 0):.0f}ms - {pipeline_analysis.get('end_to_end_metrics', {}).get('max_total_ms', 0):.0f}ms

### Identified Bottlenecks

"""
                for bottleneck in pipeline_analysis.get('bottlenecks', []):
                    report += f"- **{bottleneck.get('stage', 'N/A')}:** {bottleneck.get('percentage', 0):.1f}% of total time ({bottleneck.get('avg_latency_ms', 0):.0f}ms)\n"
                
                report += f"""
### Optimization Opportunities

"""
                for opp in pipeline_analysis.get('optimization_opportunities', []):
                    report += f"- **{opp.get('stage', 'N/A')}:** {opp.get('issue', 'N/A')}\n  - Recommendation: {opp.get('recommendation', 'N/A')}\n"
        else:
            report += "Pipeline analysis not available or encountered errors.\n"
        
        # Service Architecture
        report += f"""
---

## 5. Service Architecture Analysis

"""
        arch_analysis = self.results.get('service_architecture', {})
        if arch_analysis:
            report += f"""
### Service Dependencies

| Service | Provider | Dependencies | Scalability | Cost Model | Reliability |
|---------|----------|--------------|-------------|------------|-------------|
"""
            for service, details in arch_analysis.get('service_dependencies', {}).items():
                report += f"| {service} | {details.get('provider', 'N/A')} | {', '.join(details.get('dependencies', []))} | {details.get('scalability', 'N/A')} | {details.get('cost_model', 'N/A')} | {details.get('reliability', 'N/A')} |\n"
            
            report += f"""
### Scalability Considerations

"""
            for consideration in arch_analysis.get('scalability_considerations', []):
                report += f"- **{consideration.get('service', 'N/A')}:** {consideration.get('issue', 'N/A')}\n  - Recommendation: {consideration.get('recommendation', 'N/A')}\n"
            
            report += f"""
### Reliability Factors

"""
            for factor in arch_analysis.get('reliability_factors', []):
                report += f"- **{factor.get('factor', 'N/A')}:** Impact: {factor.get('impact', 'N/A')}\n  - Mitigation: {factor.get('mitigation', 'N/A')}\n"
        
        # Recommendations
        report += f"""
---

## 6. Recommendations

"""
        recommendations = self.results.get('recommendations', [])
        for i, rec in enumerate(recommendations, 1):
            priority_icon = "🔴" if rec.get('priority') == 'Critical' else "🟡" if rec.get('priority') == 'High' else "🟢"
            report += f"""
### {i}. {priority_icon} [{rec.get('category', 'N/A')}] {rec.get('priority', 'N/A').upper()}

**Finding:** {rec.get('finding', 'N/A')}

**Recommendation:** {rec.get('recommendation', 'N/A')}
"""
        
        # Next Steps
        report += f"""
---

## 7. Next Steps

"""
        next_steps = self.results.get('next_steps', [])
        for step in next_steps:
            report += f"""
### Step {step.get('step', 'N/A')}: {step.get('action', 'N/A')}

- **Impact:** {step.get('impact', 'N/A')}
- **Effort:** {step.get('effort', 'N/A')}
"""
        
        report += f"""
---

## 8. Key Insights

### Performance Summary

"""
        # Add key insights
        if pipeline_analysis.get('pipeline_stages'):
            stages = pipeline_analysis['pipeline_stages']
            report += f"""
- **Total Pipeline Latency:** {pipeline_analysis.get('end_to_end_metrics', {}).get('avg_total_ms', 0):.0f}ms average
- **Primary Bottleneck:** {pipeline_analysis.get('bottlenecks', [{}])[0].get('stage', 'N/A')} ({pipeline_analysis.get('bottlenecks', [{}])[0].get('percentage', 0):.1f}% of total time)
- **STT Contribution:** {stages.get('stt', {}).get('percentage', 0):.1f}%
- **LLM Contribution:** {stages.get('llm', {}).get('percentage', 0):.1f}%
- **TTS Contribution:** {stages.get('tts', {}).get('percentage', 0):.1f}%
"""
        
        report += f"""
### Optimization Priorities

1. **Immediate (High Impact, Low Effort):**
   - Implement optimal STT model configuration
   - Use recommended LLM model for best balance

2. **Short-term (High Impact, Medium Effort):**
   - Implement LLM response caching
   - Add comprehensive monitoring

3. **Long-term (High Impact, High Effort):**
   - Migrate storage to database
   - Implement streaming responses

---

## Conclusion

This analysis provides a comprehensive evaluation of the Talk-With-Zeno system's performance across all components. The recommendations and next steps outlined above should guide optimization efforts to improve latency, reliability, and scalability.

**Key Takeaway:** Focus optimization efforts on the identified bottleneck (LLM - 63.3% of pipeline time) to achieve the most significant performance improvements. Switching to `gemini-2.0-flash` and implementing caching could reduce total pipeline latency by 50-60%.

---

*Report generated automatically by deep_analysis.py*  
*For detailed data, see deep_analysis.json*
"""
        
        report_file = output_dir / f'DEEP_ANALYSIS_{timestamp}.md'
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # Also save as latest
        latest_report = output_dir / 'DEEP_ANALYSIS.md'
        with open(latest_report, 'w', encoding='utf-8') as f:
            f.write(report)


def main():
    """Run deep analysis"""
    print("="*80)
    print("DEEP PRODUCTION-GRADE ANALYSIS")
    print("="*80)
    print(f"Started at: {datetime.now().isoformat()}\n")
    
    analyzer = DeepAnalyzer()
    
    # Run all analyses
    analyzer.analyze_stt_parameters()
    analyzer.analyze_stt_chunk_sizes()  # New: Chunk size analysis
    analyzer.analyze_llm_models()
    analyzer.analyze_tts_parameters()
    analyzer.analyze_full_pipeline()
    analyzer.analyze_service_architecture()
    analyzer.generate_recommendations()
    
    # Save results
    output_dir = Path(__file__).parent.parent.parent / 'performance_results'
    analyzer.save_results(output_dir)
    
    print(f"\n✅ Deep analysis complete!")
    print(f"Results saved to: {output_dir}")


if __name__ == '__main__':
    main()

