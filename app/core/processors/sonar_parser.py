import json
from typing import Dict, List


class SonarParser:
    """Parses SonarQube report files to extract issues and metrics for code analysis."""

    def parse(self, sonar_file: str) -> Dict:
        """Parses a SonarQube JSON file and extracts issues and metadata.

        Args:
            sonar_file (str): Path to the SonarQube report file (JSON).

        Returns:
            Dict: Parsed data containing total issues, issues list, facets, and components.

        Raises:
            ValueError: If the file cannot be read or parsed as valid JSON.
        """
        try:
            with open(sonar_file, "r") as f:
                data = json.load(f)

            issues = data.get("issues", [])
            parsed_issues = []
            for issue in issues:
                parsed_issues.append({
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
                })

            return {
                "total": data.get("total", 0),
                "issues": parsed_issues,
                "facets": data.get("facets", []),
                "components": data.get("components", []),
                "metrics": data.get("metrics", {})  # Include metrics if available
            }
        except Exception as e:
            raise ValueError(f"Failed to parse SonarQube file: {str(e)}")