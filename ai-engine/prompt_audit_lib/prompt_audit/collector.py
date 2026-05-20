"""
Prompt Spec Collector - Collects all prompt specs across LangGraph agent nodes.

Issue: #1601 (T1) - Collect all prompt specs across LangGraph agent nodes
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class PromptSpec:
    """Represents a single prompt specification."""
    
    name: str
    content: str
    file_path: str
    line_number: int
    prompt_type: str  # "system", "user", "template", "fewshot", "context"
    agent_name: str
    variables: List[str] = field(default_factory=list)
    model_hints: List[str] = field(default_factory=list)
    temperature_hint: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self) -> int:
        return hash((self.name, self.file_path, self.line_number))
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PromptSpec):
            return False
        return (
            self.name == other.name
            and self.file_path == other.file_path
            and self.line_number == other.line_number
        )


class PromptCollector:
    """
    Collects all prompt specifications across PortKit's LangGraph pipeline.
    
    Searches for:
    - System prompts in agent files
    - Prompt templates in .py files
    - Markdown prompt files in prompts/ directory
    - Configuration-driven prompts
    """
    
    PROMPT_PATTERNS = {
        "system_prompt": [
            r'system_prompt\s*=\s*"""([^"]+)"""',
            r'system_prompt\s*=\s*\'\'\'([^\']+)\'\'\'',
            r'SYSTEM_PROMPT\s*=\s*"""([^"]+)"""',
            r'SYSTEM_PROMPT\s*=\s*\'\'\'([^\']+)\'\'\'',
        ],
        "user_prompt": [
            r'user_prompt\s*=\s*"""([^"]+)"""',
            r'user_prompt\s*=\s*\'\'\'([^\']+)\'\'\'',
            r'USER_PROMPT\s*=\s*"""([^"]+)"""',
        ],
        "prompt_template": [
            r'prompt\s*=\s*ChatPromptTemplate\.from_template\(_["\'](\w+)["\']',
            r'prompt\s*=\s*["\'](\w+)["\']\s*%',
        ],
    }
    
    AGENT_DIRS = [
        "ai-engine/agents",
        "ai-engine/prompts",
        "ai-engine/services",
        "ai-engine/mmsd",
    ]
    
    AGENT_FILES = [
        "rag_agents.py",
        "logic_auditor_agent.py",
        "llm_agent_tools.py",
        "mmsd/premium_client.py",
        "mmsd/train_portkit_coder.py",
        "mmsd/evaluate.py",
    ]
    
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self.prompts: List[PromptSpec] = []
        self._agent_patterns: Dict[str, str] = {}
    
    def collect_all(self) -> List[PromptSpec]:
        """Collect all prompts across the codebase."""
        self.prompts = []
        
        # Collect from agent files
        for agent_dir in self.AGENT_DIRS:
            self._scan_directory(self.base_path / agent_dir)
        
        # Collect markdown prompts
        self._collect_markdown_prompts()
        
        # Extract variables from prompts
        self._extract_variables()
        
        return self.prompts
    
    def _scan_directory(self, directory: Path) -> None:
        """Recursively scan directory for prompt specs."""
        if not directory.exists():
            return
        
        for file_path in directory.rglob("*.py"):
            self._extract_prompts_from_file(file_path)
    
    def _extract_prompts_from_file(self, file_path: Path) -> None:
        """Extract prompts from a Python file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            
            # Extract system prompts
            self._find_system_prompts(file_path, content, lines)
            
            # Extract prompt templates
            self._find_prompt_templates(file_path, content, lines)
            
            # Extract hardcoded prompt strings
            self._find_hardcoded_prompts(file_path, content, lines)
            
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    
    def _find_system_prompts(
        self, file_path: Path, content: str, lines: List[str]
    ) -> None:
        """Find system prompt definitions."""
        # Multi-line string patterns for system prompts
        patterns = [
            # (system_prompt|SYSTEM_PROMPT) = """...""" or '''...'''
            (r'(system_prompt|SYSTEM_PROMPT)\s*=\s*"""(.*?)"""', 'triple_double'),
            (r'(system_prompt|SYSTEM_PROMPT)\s*=\s*\'\'\'(.*?)\'\'\'', 'triple_single'),
        ]
        
        for pattern, quote_type in patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                prompt_name = match.group(1).lower()
                prompt_content = match.group(2).strip()
                
                # Determine line number
                line_num = content[:match.start()].count("\n") + 1
                
                # Get agent name from file path
                agent_name = self._get_agent_name_from_path(file_path)
                
                # Skip empty or very short prompts
                if len(prompt_content) < 10:
                    continue
                
                spec = PromptSpec(
                    name=prompt_name,
                    content=prompt_content,
                    file_path=str(file_path),
                    line_number=line_num,
                    prompt_type="system",
                    agent_name=agent_name,
                )
                self.prompts.append(spec)
    
    def _find_prompt_templates(
        self, file_path: Path, content: str, lines: List[str]
    ) -> None:
        """Find ChatPromptTemplate patterns and template string definitions."""
        # Pattern for _NAME_PROMPT = ( ... ) format
        template_pattern = r'(_[\w]+_PROMPT)\s*=\s*\(\s*[\"\'](.*?)[\"\']\s*\)'
        
        for match in re.finditer(template_pattern, content, re.DOTALL):
            prompt_name = match.group(1)
            prompt_content = match.group(2).strip()
            
            line_num = content[:match.start()].count("\n") + 1
            agent_name = self._get_agent_name_from_path(file_path)
            
            # Extract variables from template
            variables = re.findall(r'\{(\w+)\}', prompt_content)
            
            spec = PromptSpec(
                name=prompt_name,
                content=prompt_content,
                file_path=str(file_path),
                line_number=line_num,
                prompt_type="template",
                agent_name=agent_name,
                variables=list(set(variables)),
            )
            self.prompts.append(spec)
    
    def _find_hardcoded_prompts(
        self, file_path: Path, content: str, lines: List[str]
    ) -> None:
        """Find inline prompt strings in code."""
        # Pattern for multi-line docstring-style prompts
        # Look for "You are..." or similar role definitions
        docstring_pattern = r'"""(You\s+are[^"]+)"""'
        
        for match in re.finditer(docstring_pattern, content, re.DOTALL):
            prompt_content = match.group(1).strip()
            if len(prompt_content) > 50:  # Filter out short strings
                line_num = content[:match.start()].count("\n") + 1
                agent_name = self._get_agent_name_from_path(file_path)
                
                # Extract variables
                variables = re.findall(r'\{(\w+)\}', prompt_content)
                
                spec = PromptSpec(
                    name=f"prompt_{len(self.prompts) + 1}",
                    content=prompt_content,
                    file_path=str(file_path),
                    line_number=line_num,
                    prompt_type="system",
                    agent_name=agent_name,
                    variables=list(set(variables)),
                )
                self.prompts.append(spec)
        
        # Also check for '''You are...''' pattern
        docstring_pattern2 = r"'''(You\s+are[^']+)'''"
        
        for match in re.finditer(docstring_pattern2, content, re.DOTALL):
            prompt_content = match.group(1).strip()
            if len(prompt_content) > 50:
                line_num = content[:match.start()].count("\n") + 1
                agent_name = self._get_agent_name_from_path(file_path)
                variables = re.findall(r'\{(\w+)\}', prompt_content)
                
                spec = PromptSpec(
                    name=f"prompt_{len(self.prompts) + 1}",
                    content=prompt_content,
                    file_path=str(file_path),
                    line_number=line_num,
                    prompt_type="system",
                    agent_name=agent_name,
                    variables=list(set(variables)),
                )
                self.prompts.append(spec)
    
    def _collect_markdown_prompts(self) -> None:
        """Collect prompts from markdown files."""
        prompts_dir = self.base_path / "ai-engine" / "prompts"
        
        if not prompts_dir.exists():
            return
        
        for md_file in prompts_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            
            spec = PromptSpec(
                name=md_file.stem,
                content=content,
                file_path=str(md_file),
                line_number=1,
                prompt_type="markdown",
                agent_name="rag_service",
            )
            self.prompts.append(spec)
    
    def _get_agent_name_from_path(self, file_path: Path) -> str:
        """Extract agent name from file path."""
        parts = file_path.parts
        if "agents" in parts:
            idx = parts.index("agents")
            if len(parts) > idx + 1:
                return parts[idx + 1]
        return "unknown"
    
    def _extract_variables(self) -> None:
        """Extract template variables from prompt content."""
        for spec in self.prompts:
            # Find {variable} patterns
            variables = re.findall(r'\{(\w+)\}', spec.content)
            spec.variables = list(set(variables))
    
    def get_prompts_by_agent(self, agent_name: str) -> List[PromptSpec]:
        """Get all prompts for a specific agent."""
        return [p for p in self.prompts if p.agent_name == agent_name]
    
    def get_prompts_by_type(self, prompt_type: str) -> List[PromptSpec]:
        """Get all prompts of a specific type."""
        return [p for p in self.prompts if p.prompt_type == prompt_type]
    
    def get_prompt_summary(self) -> Dict[str, Any]:
        """Get summary statistics of collected prompts."""
        return {
            "total": len(self.prompts),
            "by_type": {
                pt: len(self.get_prompts_by_type(pt))
                for pt in set(p.prompt_type for p in self.prompts)
            },
            "by_agent": {
                agent: len(self.get_prompts_by_agent(agent))
                for agent in set(p.agent_name for p in self.prompts)
            },
            "files_with_prompts": len(set(p.file_path for p in self.prompts)),
        }