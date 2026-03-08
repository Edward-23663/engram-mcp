import aiohttp
import json
from typing import Optional, List, Dict, Any
from app.core.config import get_settings

settings = get_settings()


class LLMService:
    def __init__(self):
        self.base_url = settings.LITELLM_BASE_URL
        self.api_key = settings.LITELLM_API_KEY
        self.embed_model = settings.LITELLM_EMBED_MODEL
        self.chat_model = settings.LITELLM_CHAT_MODEL
    
    async def get_embedding(self, text: str) -> List[float]:
        """Get text embedding using litellm"""
        url = f"{self.base_url}/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.embed_model,
            "input": text
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise Exception(f"Embedding failed: {error}")
                result = await resp.json()
                return result["data"][0]["embedding"]
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """Get chat completion using litellm"""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        if system:
            messages = [{"role": "system", "content": system}] + messages
        
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise Exception(f"Chat completion failed: {error}")
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
    
    async def classify_memory_type(self, content: str) -> str:
        """Classify memory type: episodic, semantic, or procedural"""
        system_prompt = """You are a memory classifier. Classify the following memory into one of these categories:
- episodic: specific events, experiences, moments in time
- semantic: facts, knowledge, concepts, general truths
- procedural: skills, procedures, how-to knowledge, actions/sequences

Respond with only one word: episodic, semantic, or procedural."""
        
        messages = [{"role": "user", "content": f"Classify this memory:\n\n{content[:500]}"}]
        
        try:
            result = await self.chat_completion(messages, system=system_prompt, temperature=0.3, max_tokens=20)
            result = result.strip().lower()
            if result in ["episodic", "semantic", "procedural"]:
                return result
            return "semantic"
        except Exception:
            return "semantic"
    
    async def evaluate_quality(self, content: str) -> float:
        """Evaluate memory quality score (0-1)"""
        system_prompt = """You are a memory quality evaluator. Rate the following memory on a scale of 0 to 1 based on its potential long-term value.
Consider:
- Is this unique information or easily derivable?
- Does it represent a significant decision, lesson, or preference?
- Is it actionable or insightful?

Respond with only a number between 0 and 1."""
        
        messages = [{"role": "user", "content": f"Rate this memory:\n\n{content[:500]}"}]
        
        try:
            result = await self.chat_completion(messages, system=system_prompt, temperature=0.3, max_tokens=10)
            result = result.strip()
            score = float(result)
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5
    
    async def should_promote_to_working(self, content: str, context: dict) -> bool:
        """Decide if memory should be promoted from Buffer to Working layer"""
        system_prompt = """You are a memory promotion gatekeeper. Determine if this memory is important enough to promote from temporary storage (Buffer) to working memory (Working layer).
Consider:
- Does it contain a decision, preference, or important context?
- Is it likely to be referenced again?
- Does it represent useful context for future interactions?

Respond with only YES or NO."""
        
        messages = [{"role": "user", "content": f"Should this memory be promoted?\n\nContent: {content[:500]}\nContext: {context}"}]
        
        try:
            result = await self.chat_completion(messages, system=system_prompt, temperature=0.3, max_tokens=5)
            return "YES" in result.upper()
        except Exception:
            return False
    
    async def should_promote_to_core(self, content: str, context: dict, quality_score: float) -> bool:
        """Decide if memory should be promoted from Working to Core layer"""
        system_prompt = """You are a memory archive gatekeeper. Determine if this memory should be promoted from working memory to permanent core memory (Core layer - never deleted).
Consider:
- Is this a core identity, principle, or fundamental truth?
- Would losing this be a significant loss of identity or capability?
- Is this referenced frequently or represents a key preference/value?

Respond with only YES or NO."""
        
        messages = [{"role": "user", "content": f"Should this be archived permanently?\n\nContent: {content[:500]}\nContext: {context}\nQuality Score: {quality_score}"}]
        
        try:
            result = await self.chat_completion(messages, system=system_prompt, temperature=0.3, max_tokens=5)
            return "YES" in result.upper()
        except Exception:
            return False
    
    async def merge_memories(self, memory1: str, memory2: str) -> str:
        """Merge two similar memories into one coherent memory"""
        system_prompt = """You are a memory merger. Combine these two similar memories into one coherent, non-redundant memory. Preserve the unique context from both."""
        
        messages = [{"role": "user", "content": f"Memory 1:\n{memory1}\n\nMemory 2:\n{memory2}\n\nMerge into one memory:"}]
        
        try:
            return await self.chat_completion(messages, system=system_prompt, temperature=0.5, max_tokens=500)
        except Exception:
            return memory1
    
    async def distill_topic(self, memories: List[str], topic_name: str) -> str:
        """Distill multiple memories into a topic summary"""
        system_prompt = """You are a knowledge distiller. Create a concise, comprehensive summary of these related memories that captures the essence of them all."""
        
        content = "\n\n".join([f"Memory {i+1}: {m}" for i, m in enumerate(memories)])
        messages = [{"role": "user", "content": f"Topic: {topic_name}\n\nMemories:\n{content}\n\nCreate a distilled summary:"}]
        
        try:
            return await self.chat_completion(messages, system=system_prompt, temperature=0.5, max_tokens=500)
        except Exception:
            return f"Summary of {len(memories)} memories about {topic_name}"
    
    async def name_topic(self, memories: List[str]) -> str:
        """Generate a name for a cluster of memories"""
        system_prompt = """You are a topic namer. Generate a short, descriptive name (2-5 words) for this cluster of memories."""
        
        content = "\n".join([f"- {m[:100]}" for m in memories[:10]])
        messages = [{"role": "user", "content": f"Generate a name for:\n{content}"}]
        
        try:
            result = await self.chat_completion(messages, system=system_prompt, temperature=0.5, max_tokens=20)
            return result.strip()
        except Exception:
            return "Unknown Topic"
    
    async def evaluate_importance(self, content: str, context: dict, access_count: int = 0) -> tuple[float, str]:
        """Evaluate memory importance score (0-1) and reason
        
        Returns:
            tuple: (importance_score, reason)
        """
        system_prompt = """You are a memory importance evaluator. Evaluate how important this memory is for long-term retention.
Consider:
- Is this a critical decision, preference, or key learning?
- Does it represent core identity or values?
- Would losing this significantly impact future performance?
- Is this referenced frequently or has high access count?

Provide a JSON response with:
- score: number between 0 and 1
- reason: brief explanation (max 100 characters)"""
        
        messages = [{"role": "user", "content": f"""Evaluate importance:
Content: {content[:500]}
Context: {context}
Access Count: {access_count}"""}]
        
        try:
            result = await self.chat_completion(
                messages, 
                system=system_prompt, 
                temperature=0.3, 
                max_tokens=200
            )
            import json
            import re
            
            json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                score = float(data.get('score', 0.5))
                reason = str(data.get('reason', ''))[:100]
                return max(0.0, min(1.0, score)), reason
            
            return 0.5, "Evaluated by LLM"
        except Exception:
            return 0.5, "Evaluation failed"
    
    async def should_mark_important(
        self, 
        content: str, 
        context: dict, 
        quality_score: float,
        access_count: int = 0,
        memory_type: str = "semantic"
    ) -> tuple[bool, str]:
        """Determine if memory should be marked as permanently important
        
        Returns:
            tuple: (should_mark, reason)
        """
        system_prompt = """You are a critical memory detector. Determine if this memory is CRITICAL enough to be marked as permanently important (never deleted).

IMPORTANT CRITERIA (all must be true or score very high):
- Core identity/values (who am I, what do I believe)
- Critical decisions (major life/work decisions)
- Key learnings (important lessons learned)
- Unique expertise (specialized knowledge/skills)
- High-value preferences (strong user preferences)

Respond with JSON:
- mark_important: boolean
- reason: brief explanation (max 100 characters)"""
        
        messages = [{"role": "user", "content": f"""Should this be permanently important?
Content: {content[:500]}
Context: {context}
Quality Score: {quality_score}
Access Count: {access_count}
Memory Type: {memory_type}"""}]
        
        try:
            result = await self.chat_completion(
                messages, 
                system=system_prompt, 
                temperature=0.3, 
                max_tokens=200
            )
            import json
            import re
            
            json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                should_mark = bool(data.get('mark_important', False))
                reason = str(data.get('reason', ''))[:100]
                return should_mark, reason
            
            return False, ""
        except Exception:
            return False, ""
    
    async def detect_auto_protection(
        self,
        content: str,
        access_count: int,
        quality_score: float,
        memory_type: str
    ) -> tuple[bool, str]:
        """Auto-detect if memory should be protected based on patterns
        
        Returns:
            tuple: (should_protect, source)
        """
        if memory_type == "semantic" and quality_score >= 0.8:
            return True, "high_quality_semantic"
        
        if memory_type == "procedural" and quality_score >= 0.7:
            return True, "procedural_skill"
        
        if access_count >= 10:
            return True, "frequent_access"
        
        if "important" in content.lower() or "critical" in content.lower() or "key" in content.lower():
            if quality_score >= 0.6:
                return True, "content_keywords"
        
        return False, ""


llm_service = LLMService()


async def get_llm_service():
    return llm_service
