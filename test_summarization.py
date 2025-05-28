#!/usr/bin/env python3
"""
Test script for the summarization service
"""

import asyncio
import os
from dotenv import load_dotenv
from summarization_service import SummarizationService

load_dotenv()

async def test_summarization():
    # Initialize the service
    service = SummarizationService()
    
    # Test transcription
    test_transcription = """
    Hello everyone, welcome to today's presentation about artificial intelligence and machine learning.
    
    Today we'll cover three main topics:
    1. The fundamentals of neural networks
    2. Recent breakthroughs in large language models
    3. Practical applications in various industries
    
    Let's start with neural networks. A neural network is a computational model inspired by the human brain.
    It consists of layers of interconnected nodes or neurons that process information. 
    
    Moving on to large language models, we've seen incredible progress in the past few years.
    Models like GPT-4 and Claude have demonstrated remarkable capabilities in understanding and generating human-like text.
    
    Finally, let's talk about applications. AI is being used in healthcare for diagnosis, in finance for fraud detection,
    and in transportation for autonomous vehicles. The possibilities are endless.
    
    In conclusion, AI and ML are transforming how we work and live. Thank you for your attention.
    """
    
    print("Testing English summarization...")
    result = await service.summarize(test_transcription, language='en')
    if result['success']:
        print("✅ English summarization successful!")
        print(f"Summary:\n{result['summary']}\n")
    else:
        print(f"❌ English summarization failed: {result.get('error')}")
    
    print("\nTesting Russian summarization...")
    result = await service.summarize(test_transcription, language='ru')
    if result['success']:
        print("✅ Russian summarization successful!")
        print(f"Summary:\n{result['summary']}\n")
    else:
        print(f"❌ Russian summarization failed: {result.get('error')}")
    
    print("\nTesting with custom prompt...")
    result = await service.summarize(
        test_transcription, 
        language='en',
        custom_prompt="Focus on the practical applications mentioned"
    )
    if result['success']:
        print("✅ Custom prompt summarization successful!")
        print(f"Summary:\n{result['summary']}\n")
    else:
        print(f"❌ Custom prompt summarization failed: {result.get('error')}")

if __name__ == "__main__":
    # Check if API key is set
    if not os.getenv('ANTHROPIC_API_KEY'):
        print("❌ Error: ANTHROPIC_API_KEY not set in .env file")
        exit(1)
    
    asyncio.run(test_summarization())