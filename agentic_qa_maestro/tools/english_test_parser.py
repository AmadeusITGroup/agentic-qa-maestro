"""
English Test Case Parser
Converts plain English test cases to structured format
"""

import re
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class TestStep:
    """Represents a single test step"""
    step_number: int
    description: str
    action: str  # click, fill, navigate, verify, wait, screenshot
    target: Optional[str] = None  # CSS selector or element description
    value: Optional[str] = None  # Value to fill or verify
    wait_time: Optional[int] = None  # Wait time in seconds


@dataclass
class TestCase:
    """Represents a formatted test case"""
    test_id: str
    title: str
    description: str
    priority: str  # High, Medium, Low
    steps: List[TestStep]
    expected_result: str
    preconditions: Optional[str] = None
    tags: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'test_id': self.test_id,
            'title': self.title,
            'description': self.description,
            'priority': self.priority,
            'steps': [asdict(step) for step in self.steps],
            'expected_result': self.expected_result,
            'preconditions': self.preconditions,
            'tags': self.tags or []
        }


class EnglishTestCaseParser:
    """Parser for converting English text test cases to structured format"""

    def __init__(self):
        self.test_cases: List[TestCase] = []

    def parse(self, text: str) -> List[TestCase]:
        """
        Parse English test cases from text
        
        Supports multiple formats:
        - Markdown-style headers (## Test Case)
        - Numbered lists
        - Narrative format with clear sections
        
        Args:
            text: Raw test case text
            
        Returns:
            List of parsed TestCase objects
        """
        self.test_cases = []
        
        # Split by test case markers
        test_blocks = self._split_test_blocks(text)
        
        for block in test_blocks:
            test_case = self._parse_test_block(block)
            if test_case:
                self.test_cases.append(test_case)
        
        # Auto-generate test IDs if missing
        for i, tc in enumerate(self.test_cases, 1):
            if not tc.test_id or tc.test_id == "":
                tc.test_id = f"TC{i:03d}"
        
        return self.test_cases

    def _split_test_blocks(self, text: str) -> List[str]:
        """Split text into individual test case blocks"""
        # Format 1: ## Test Case N  or  ### Test Case N
        pattern = r'(?:^|\n)(?:##|###)\s+(?:Test\s+)?Case'
        blocks = re.split(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        if len(blocks) > 1:
            return [b.strip() for b in blocks[1:] if b.strip()]

        # Format 2: # TC001 - Title  or  # TC001: Title  or  # TC001 Title
        pattern = r'(?:^|\n)#\s+TC\d+'
        blocks = re.split(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        if len(blocks) > 1:
            # Re-extract the TC ID from the original text to include in each block
            ids = re.findall(r'(?:^|\n)(#\s+TC\d+[^\n]*)', text, flags=re.MULTILINE | re.IGNORECASE)
            result = []
            for i, block in enumerate(blocks[1:]):
                prefix = ids[i] if i < len(ids) else ""
                result.append((prefix + "\n" + block).strip())
            return result

        # Format 3: Test Case: Title  or  Test Case 1: Title  (plain text)
        pattern = r'(?:^|\n)Test\s+Case\s*[\d]*\s*[:\-]'
        blocks = re.split(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        if len(blocks) > 1:
            return [b.strip() for b in blocks[1:] if b.strip()]

        # Format 4: numbered blocks  1. Test Case...  2. Test Case...
        pattern = r'(?:^|\n)[\d]+\.\s+(?:Test\s+)?Case'
        blocks = re.split(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
        if len(blocks) > 1:
            return [b.strip() for b in blocks[1:] if b.strip()]

        # Format 5: separator-based --- blocks each containing ID: or Title:
        blocks = re.split(r'\n[-]{3,}\n', text)
        candidate_blocks = [b.strip() for b in blocks if b.strip() and
                            re.search(r'(?:id:|title:|step)', b, re.IGNORECASE)]
        if len(candidate_blocks) > 1:
            return candidate_blocks

        # Fall back: treat entire text as one test case
        return [text.strip()]

    def _parse_test_block(self, block: str) -> Optional[TestCase]:
        """Parse a single test case block"""
        lines = block.split('\n')
        
        test_id = ""
        title = ""
        description = ""
        priority = "Medium"
        preconditions = ""
        steps: List[TestStep] = []
        expected_result = ""
        current_section = None
        step_counter = 1
        step_accumulator = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Extract ID + title from # TC001 - Title  or  # TC001: Title  or  # TC001 Title
            header_match = re.match(r'^#+\s+(TC\d+)\s*[-:–]?\s*(.*)', line, re.IGNORECASE)
            if header_match:
                test_id = header_match.group(1).strip()
                possible_title = header_match.group(2).strip()
                if possible_title:
                    title = possible_title
                continue

            # Extract test ID
            if 'id:' in line.lower() or 'test id:' in line.lower():
                test_id = re.sub(r'(?:test\s+)?id:\s*', '', line, flags=re.IGNORECASE).strip()
                continue

            # Extract title
            if 'title:' in line.lower():
                title = re.sub(r'title:\s*', '', line, flags=re.IGNORECASE).strip()
                continue
            
            # Extract description
            if 'description:' in line.lower():
                description = re.sub(r'description:\s*', '', line, flags=re.IGNORECASE).strip()
                current_section = "description"
                continue
            
            # Extract priority
            if 'priority:' in line.lower():
                priority_str = re.sub(r'priority:\s*', '', line, flags=re.IGNORECASE).strip().lower()
                if any(p in priority_str for p in ['high', 'critical', 'urgent']):
                    priority = "High"
                elif any(p in priority_str for p in ['low', 'minor']):
                    priority = "Low"
                else:
                    priority = "Medium"
                continue
            
            # Extract preconditions
            if 'precondition' in line.lower():
                preconditions = re.sub(r'preconditions?:\s*', '', line, flags=re.IGNORECASE).strip()
                current_section = "preconditions"
                continue
            
            # Section markers
            if 'step' in line.lower() and ':' in line:
                current_section = "steps"
                continue
            
            if 'expected' in line.lower() and ('result' in line.lower() or 'outcome' in line.lower()):
                # Flush any pending step before switching sections
                if step_accumulator and current_section == "steps":
                    step = self._parse_step(step_accumulator, step_counter)
                    if step:
                        steps.append(step)
                        step_counter += 1
                    step_accumulator = ""
                current_section = "expected_result"
                # Capture inline value: "Expected Result: some text"
                inline = re.sub(r'^expected\s+(?:result|outcome)\s*:\s*', '', line, flags=re.IGNORECASE).strip()
                if inline:
                    expected_result = inline
                continue
            
            # Skip separator lines
            if re.match(r'^[-]{3,}$', line):
                continue

            # Auto-detect numbered steps even without a "Steps:" header
            if current_section not in ("steps", "expected_result") and re.match(r'^\d+[\.\)]\s+', line):
                current_section = "steps"

            # Parse steps
            if current_section == "steps":
                step_match = re.match(r'^(?:\d+[\.\)]\s+)?(.+)', line)
                if step_match:
                    if step_accumulator:
                        step = self._parse_step(step_accumulator, step_counter)
                        if step:
                            steps.append(step)
                            step_counter += 1
                    step_accumulator = step_match.group(1)
                else:
                    step_accumulator += " " + line

            elif current_section == "expected_result":
                expected_result += " " + line if expected_result else line

            elif current_section == "description":
                description += " " + line if description else line

            elif current_section == "preconditions":
                preconditions += " " + line if preconditions else line

            else:
                # No section yet — treat first non-field line as the title, rest as description
                if not title and not re.match(r'^\d+[\.\)]\s+', line):
                    title = line
                elif title:
                    description += " " + line if description else line
        
        # Don't forget last step
        if step_accumulator and current_section == "steps":
            step = self._parse_step(step_accumulator, step_counter)
            if step:
                steps.append(step)
        
        # Require at least steps or some content to be valid
        if not title and not description and not steps:
            return None

        # Derive title from first non-empty line if still missing
        _section_keywords = re.compile(
            r'^(?:steps?|expected\s+(?:result|outcome)|description|priority|preconditions?|tags?)\s*:',
            re.IGNORECASE
        )
        if not title:
            for l in lines:
                l = l.strip()
                if (l
                        and not re.match(r'^\d+[\.]\s+', l)
                        and not re.match(r'^[-]{3,}$', l)
                        and not _section_keywords.match(l)):
                    title = l
                    break
            if not title:
                title = "Test Case"

        # If no explicit steps found, try to extract from narrative description
        if not steps and description:
            steps = self._extract_steps_from_narrative(description)
        
        return TestCase(
            test_id=test_id,
            title=title,
            description=description,
            priority=priority,
            steps=steps,
            expected_result=expected_result,
            preconditions=preconditions if preconditions else None
        )

    def _parse_step(self, step_text: str, step_num: int) -> Optional[TestStep]:
        """Parse a single test step"""
        step_text = step_text.strip()
        if not step_text:
            return None
        
        # Detect action type
        action = self._detect_action(step_text)
        target = self._extract_target(step_text, action)
        value = self._extract_value(step_text, action)
        wait_time = self._extract_wait_time(step_text)
        
        return TestStep(
            step_number=step_num,
            description=step_text,
            action=action,
            target=target,
            value=value,
            wait_time=wait_time
        )

    def _detect_action(self, text: str) -> str:
        """Detect the action type from step text"""
        text_lower = text.lower()
        
        if any(w in text_lower for w in ['click', 'press', 'select', 'open', 'tap']):
            return "click"
        elif any(w in text_lower for w in ['fill', 'enter', 'type', 'input', 'set']):
            return "fill"
        elif any(w in text_lower for w in ['navigate', 'go to', 'visit', 'open url']):
            return "navigate"
        elif any(w in text_lower for w in ['verify', 'check', 'assert', 'should', 'see', 'appear']):
            return "verify"
        elif any(w in text_lower for w in ['wait', 'delay', 'pause']):
            return "wait"
        elif any(w in text_lower for w in ['screenshot', 'capture', 'snap']):
            return "screenshot"
        else:
            return "action"

    def _extract_target(self, text: str, action: str) -> Optional[str]:
        """Extract target element (selector or description)"""
        # Look for quoted strings or selectors
        quoted_match = re.search(r'["\']([^"\']+)["\']', text)
        if quoted_match:
            return quoted_match.group(1)
        
        # Look for common patterns like "button", "field", "link"
        common_patterns = {
            'click': [r'click\s+(?:on\s+)?(?:the\s+)?(\w+(?:\s+\w+)*)', r'on\s+(?:the\s+)?(\w+(?:\s+\w+)*)'],
            'fill': [r'fill\s+(?:in\s+)?(?:the\s+)?(\w+(?:\s+\w+)*)', r'(?:the\s+)?(\w+(?:\s+\w+)*)\s+field'],
            'verify': [r'(?:see|verify|check)\s+(?:that\s+)?(?:the\s+)?(\w+(?:\s+\w+)*)', r'(?:the\s+)?(\w+(?:\s+\w+)*)\s+(?:is|appears)'],
        }
        
        patterns = common_patterns.get(action, [])
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None

    def _extract_value(self, text: str, action: str) -> Optional[str]:
        """Extract the value to fill or verify"""
        if action == "fill":
            # Look for "with <value>" pattern
            match = re.search(r'with\s+["\']?([^"\']+)["\']?(?:\s|$)', text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        elif action == "verify":
            # Look for "should see <value>" or "contains <value>"
            match = re.search(r'(?:should\s+)?(?:see|contain|be)\s+["\']?([^"\']+)["\']?(?:\s|$)', text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None

    def _extract_wait_time(self, text: str) -> Optional[int]:
        """Extract wait time in seconds"""
        match = re.search(r'wait\s+(?:for\s+)?(\d+)\s+(?:second|sec)', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _extract_steps_from_narrative(self, narrative: str) -> List[TestStep]:
        """Extract steps from narrative format (when no explicit steps are provided)"""
        steps = []
        
        # Split by common conjunctions and sentence boundaries
        sentences = re.split(r'(?:^|\s)(?:then|and|next|finally)\s+', narrative, flags=re.IGNORECASE)
        
        for i, sentence in enumerate(sentences, 1):
            sentence = sentence.strip()
            if sentence:
                step = self._parse_step(sentence, i)
                if step:
                    steps.append(step)
        
        return steps


def parse_english_test_cases(text: str) -> List[Dict[str, Any]]:
    """
    Convenience function to parse English test cases and return as dicts
    
    Args:
        text: Raw test case text
        
    Returns:
        List of test case dictionaries
    """
    parser = EnglishTestCaseParser()
    test_cases = parser.parse(text)
    return [tc.to_dict() for tc in test_cases]
