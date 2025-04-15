import json
from typing import Dict, List

class SonarParser:
    def parse(self, sonar_file: str) -> Dict:
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
                "components": data.get("components", [])
            }
        except Exception as e:
            raise ValueError(f"Failed to parse SonarQube file: {str(e)}")