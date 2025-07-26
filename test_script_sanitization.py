#!/usr/bin/env python3
"""
Test script for text sanitization functionality
"""
import re

def sanitize_script_text(text: str) -> str:
    """
    Sanitize script text to remove markdown formatting and ensure natural speech.
    Removes asterisks and other formatting while preserving natural punctuation.
    """
    # Remove all asterisks (markdown bold/italic)
    text = re.sub(r'\*+', '', text)
    
    # Remove markdown headers (# ## ###)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    
    # Remove markdown list markers (- * +) and preserve proper spacing
    text = re.sub(r'^\s*[-\*\+]\s+', '', text, flags=re.MULTILINE)
    
    # Remove markdown code blocks and inline code
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)  # Keep content inside inline code
    
    # Remove markdown links [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Clean up whitespace after code block removal
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Max 2 consecutive line breaks
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single space
    
    # Fix spacing around periods when followed by code blocks
    text = re.sub(r'\.(\w)', r'. \1', text)
    
    # Ensure proper sentence spacing
    text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)
    
    return text.strip()

def test_sanitization():
    """Test various markdown and formatting removals"""
    
    test_cases = [
        {
            "name": "Asterisk removal",
            "input": "This is *bold* text and **very bold** text with ***emphasis***.",
            "expected": "This is bold text and very bold text with emphasis."
        },
        {
            "name": "Headers removal", 
            "input": "# Main Title\n## Subtitle\n### Sub-subtitle\nRegular text",
            "expected": "Main Title\nSubtitle\nSub-subtitle\nRegular text"
        },
        {
            "name": "List markers removal",
            "input": "- First item\n* Second item\n+ Third item\nRegular text",
            "expected": "First item\nSecond item\nThird item\nRegular text"
        },
        {
            "name": "Code blocks removal",
            "input": "Here's some code:\n```python\nprint('hello')\n```\nAnd `inline code` here.",
            "expected": "Here's some code:\n\nAnd inline code here."
        },
        {
            "name": "Links removal",
            "input": "Check out [this website](https://example.com) and [another link](http://test.com).",
            "expected": "Check out this website and another link."
        },
        {
            "name": "Multiple whitespace normalization",
            "input": "Too    many     spaces\n\n\n\nToo many lines",
            "expected": "Too many spaces\n\nToo many lines"
        },
        {
            "name": "Sentence spacing",
            "input": "First sentence.Second sentence!Third sentence?Fourth sentence.",
            "expected": "First sentence. Second sentence! Third sentence? Fourth sentence."
        },
        {
            "name": "Complex example with multiple issues",
            "input": "# Podcast Episode\n\n*Welcome* to **our show**!\n\n- Point one\n- Point *two*\n\nVisit [our website](https://example.com) for more.```\ncode here\n```End.",
            "expected": "Podcast Episode\n\nWelcome to our show!\n\nPoint one\nPoint two\n\nVisit our website for more. End."
        }
    ]
    
    print("🧪 Running script sanitization tests...\n")
    
    all_passed = True
    for i, test in enumerate(test_cases, 1):
        result = sanitize_script_text(test["input"])
        passed = result == test["expected"]
        all_passed = all_passed and passed
        
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} Test {i}: {test['name']}")
        
        if not passed:
            print(f"  Input:    '{test['input']}'")
            print(f"  Expected: '{test['expected']}'") 
            print(f"  Got:      '{result}'")
        print()
    
    if all_passed:
        print("🎉 All tests passed! Script sanitization is working correctly.")
    else:
        print("❌ Some tests failed. Please check the sanitization function.")
    
    return all_passed

if __name__ == "__main__":
    test_sanitization()