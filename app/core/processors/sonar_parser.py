import json
import os
import re
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class SonarParser:
    """Parses SonarQube reports and estimates documentation coverage for any language."""

    # Regex patterns for comments
    SINGLE_LINE_COMMENT = r'^\s*//.*$'
    MULTI_LINE_C_STYLE = r'/\*[\s\S]*?\*/'
    PYTHON_HASH_COMMENT = r'^\s*#.*$'
    PYTHON_DOCSTRING = r'"""[\s\S]*?"""'
    PYTHON_SINGLE_QUOTE_DOCSTRING = r"'''[\s\S]*?'''"
    HTML_COMMENT = r'<!--[\s\S]*?-->'

    COMMENT_PATTERNS = {
        '.py': [
            (PYTHON_HASH_COMMENT, False),
            (PYTHON_DOCSTRING, True),
            (PYTHON_SINGLE_QUOTE_DOCSTRING, True)
        ],
        '.js': [(SINGLE_LINE_COMMENT, False), (MULTI_LINE_C_STYLE, True)],
        '.ts': [(SINGLE_LINE_COMMENT, False), (MULTI_LINE_C_STYLE, True)],
        '.html': [(HTML_COMMENT, True)],
        '.css': [(MULTI_LINE_C_STYLE, True)],
        '.java': [(SINGLE_LINE_COMMENT, False), (MULTI_LINE_C_STYLE, True)],
        '.cpp': [(SINGLE_LINE_COMMENT, False), (MULTI_LINE_C_STYLE, True)],
        '.c': [(SINGLE_LINE_COMMENT, False), (MULTI_LINE_C_STYLE, True)]
    }

    def parse(self, sonar_file: str) -> Dict:
        """Parses a SonarQube JSON file and extracts issues and metadata."""
        try:
            with open(sonar_file, "r", encoding='utf-8') as f:
                data = json.load(f)

            issues = data.get("issues", [])
            parsed_issues = [{
                "key": issue["key"],
                "rule": issue["rule"],
                "severity": issue["severity"],
                "component": issue["component"],
                "line": issue.get("line"),
                "message": issue["message"],
                "type": issue["type"],
                "effort": issue.get("effort"),
                "impacts": issue.get("impacts", []),
                "file": issue["component"].split(":")[-1] if ":" in issue["component"] else issue["component"]
            } for issue in issues]

            return {
                "total": data.get("total", 0),
                "issues": parsed_issues,
                "facets": data.get("facets", []),
                "components": data.get("components", []),
                "metrics": data.get("metrics", {})
            }
        except Exception as e:
            logger.error(f"Failed to parse SonarQube file: {str(e)}")
            raise ValueError(f"Failed to parse SonarQube file: {str(e)}")

    def _count_comments(self, content: str, patterns: List[tuple]) -> int:
        """Count comment lines for given patterns."""
        comment_lines = 0
        for pattern, is_multiline in patterns:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                comment = match.group(0)
                comment_lines += (
                    len([line for line in comment.splitlines() if line.strip()])
                    if is_multiline else 1
                )
        return comment_lines

    def get_doc_coverage(self, source_dir: str = "app") -> float:
        """Estimate documentation coverage by counting comment lines."""
        try:
            total_lines = 0
            comment_lines = 0

            for root, _, files in os.walk(source_dir):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    patterns = self.COMMENT_PATTERNS.get(ext)
                    if not patterns:
                        continue

                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        lines = content.splitlines()
                        total_lines += len([line for line in lines if line.strip()])
                        comment_lines += self._count_comments(content, patterns)
                    except Exception as e:
                        logger.warning(f"Failed to parse {file_path}: {str(e)}")

            return (comment_lines / total_lines * 100) if total_lines > 0 else 0.0
        except Exception as e:
            logger.error(f"Doc coverage calculation failed: {str(e)}")
            return 0.0