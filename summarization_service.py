import os
import logging
from typing import Dict, Optional, List
from datetime import datetime

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None

logger = logging.getLogger(__name__)

class SummarizationService:
    """Service for summarizing transcriptions using Claude API"""
    
    def __init__(self):
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.client = None
        
        if not ANTHROPIC_AVAILABLE:
            logger.warning("Anthropic module not installed. Summarization will not be available.")
            logger.warning("Run: pip install anthropic>=0.39.0")
        elif not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set, summarization will be unavailable")
        else:
            self.client = Anthropic(api_key=self.api_key)
        
        self.summarization_dir = 'summarization'
        self.system_prompts = {}
        self.glossaries = {}
        self._load_resources()
    
    def _load_resources(self):
        """Load system prompts and glossaries"""
        # Load system prompts
        prompt_files = {
            'en': 'system_prompt_simple_en.txt',
            'ru': 'system_prompt_simple_ru.txt'
        }
        
        for lang, filename in prompt_files.items():
            filepath = os.path.join(self.summarization_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.system_prompts[lang] = f.read().strip()
                logger.info(f"Loaded system prompt for {lang}")
        
        # Load glossaries
        glossary_dir = os.path.join(self.summarization_dir, 'glossary')
        if os.path.exists(glossary_dir):
            for filename in os.listdir(glossary_dir):
                if filename.endswith('.txt'):
                    lang_code = filename.replace('glossary_', '').replace('.txt', '')
                    filepath = os.path.join(glossary_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self.glossaries[lang_code] = f.read().strip()
                    logger.info(f"Loaded glossary for {lang_code}")
    
    def is_available(self) -> bool:
        """Check if summarization service is available"""
        return self.client is not None
    
    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages"""
        return list(self.system_prompts.keys())
    
    async def summarize(
        self,
        transcription: str,
        language: str = 'ru',
        custom_prompt: Optional[str] = None,
        previous_summary: Optional[str] = None,
        feedback: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Summarize a transcription
        
        Args:
            transcription: The text to summarize
            language: Target language for summary ('en' or 'ru')
            custom_prompt: Additional instructions from user
            previous_summary: Previous summary for refinement
            feedback: User feedback for summary refinement
            
        Returns:
            Dict with 'success', 'summary' and optional 'error'
        """
        try:
            if not self.is_available():
                return {
                    'success': False,
                    'error': "Summarization service not available. Please set ANTHROPIC_API_KEY"
                }
            
            if language not in self.system_prompts:
                return {
                    'success': False,
                    'error': f"Unsupported language: {language}. Supported: {self.get_supported_languages()}"
                }
            
            # Build the system prompt
            system_prompt = self.system_prompts[language]
            
            # Add glossary if available
            if language in self.glossaries:
                system_prompt += f"\n\nGLOSSARY:\n{self.glossaries[language]}"
            
            # Build the user prompt
            user_prompt_parts = []
            
            if previous_summary and feedback:
                # Refinement mode
                user_prompt_parts.append(f"Previous summary:\n{previous_summary}\n")
                user_prompt_parts.append(f"User feedback:\n{feedback}\n")
                user_prompt_parts.append("Please refine the summary based on the feedback while maintaining accuracy to the original transcription.\n")
            
            if custom_prompt:
                user_prompt_parts.append(f"Additional instructions:\n{custom_prompt}\n")
            
            user_prompt_parts.append(f"Transcription to summarize:\n{transcription}")
            user_prompt = "\n".join(user_prompt_parts)
            
            # Call Claude API
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=4096,
                temperature=0.3  # Lower temperature for more consistent summaries
            )
            
            summary = response.content[0].text
            
            return {
                'success': True,
                'summary': summary,
                'metadata': {
                    'language': language,
                    # 'timestamp': datetime.now(datetime.timezone.utc).isoformat(),
                    'timestamp': datetime.now().isoformat(),
                    'model': response.model,
                    'custom_prompt_used': bool(custom_prompt),
                    'is_refinement': bool(previous_summary and feedback)
                }
            }
            
        except Exception as e:
            logger.error(f"Error in summarization: {str(e)}")
            return {
                'success': False,
                'error': f"Failed to generate summary: {str(e)}"
            }
    
    def save_summary(self, summary: str, original_filename: str, language: str, output_dir: str = None) -> str:
        """Save summary to file and return the path"""
        if not output_dir:
            output_dir = os.path.join('temp_resources', 'summaries')
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename
        base_name = os.path.splitext(original_filename)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{base_name}_summary_{language}_{timestamp}.txt"
        filepath = os.path.join(output_dir, filename)
        
        # Save summary
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        logger.info(f"Summary saved to: {filepath}")
        return filepath

# Singleton instance
_summarization_service = None

def get_summarization_service():
    """Get singleton instance of SummarizationService"""
    global _summarization_service
    if _summarization_service is None:
        _summarization_service = SummarizationService()
    return _summarization_service