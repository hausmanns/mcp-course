#!/usr/bin/env python3
"""
Module 2: GitHub Actions Integration - STARTER CODE
Extend your PR Agent with webhook handling and MCP Prompts for CI/CD workflows.
"""

import json
import os
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent-actions")

# PR template directory (shared between starter and solution)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Default PR templates
DEFAULT_TEMPLATES = {
    "bug.md": "Bug Fix",
    "feature.md": "Feature",
    "docs.md": "Documentation",
    "refactor.md": "Refactor",
    "test.md": "Test",
    "performance.md": "Performance",
    "security.md": "Security"
}

EVENTS_FILE = Path(__file__).parent / "github_events.json"

# Type mapping for PR templates
TYPE_MAPPING = {
    "bug": "bug.md",
    "fix": "bug.md",
    "feature": "feature.md",
    "enhancement": "feature.md",
    "docs": "docs.md",
    "documentation": "docs.md",
    "refactor": "refactor.md",
    "cleanup": "refactor.md",
    "test": "test.md",
    "testing": "test.md",
    "performance": "performance.md",
    "optimization": "performance.md",
    "security": "security.md"
}


# ===== Module 1 Tools (Already includes output limiting fix from Module 1) =====

@mcp.tool()
async def analyze_file_changes(
    base_branch: str = "main",
    include_diff: bool = True,
    max_diff_lines: int = 500
) -> str:
    """Get the full diff and list of changed files in the current git repository.
    
    Args:
        base_branch: Base branch to compare against (default: main)
        include_diff: Include the full diff content (default: true)
        max_diff_lines: Maximum number of diff lines to include (default: 500)
    """
    try:
        # Get list of changed files
        files_result = subprocess.run(
            ["git", "diff", "--name-status", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Get diff statistics
        stat_result = subprocess.run(
            ["git", "diff", "--stat", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True
        )
        
        # Get the actual diff if requested
        diff_content = ""
        truncated = False
        if include_diff:
            diff_result = subprocess.run(
                ["git", "diff", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True
            )
            diff_lines = diff_result.stdout.split('\n')
            
            # Check if we need to truncate (learned from Module 1)
            if len(diff_lines) > max_diff_lines:
                diff_content = '\n'.join(diff_lines[:max_diff_lines])
                diff_content += f"\n\n... Output truncated. Showing {max_diff_lines} of {len(diff_lines)} lines ..."
                diff_content += "\n... Use max_diff_lines parameter to see more ..."
                truncated = True
            else:
                diff_content = diff_result.stdout
        
        # Get commit messages for context
        commits_result = subprocess.run(
            ["git", "log", "--oneline", f"{base_branch}..HEAD"],
            capture_output=True,
            text=True
        )
        
        analysis = {
            "base_branch": base_branch,
            "files_changed": files_result.stdout,
            "statistics": stat_result.stdout,
            "commits": commits_result.stdout,
            "diff": diff_content if include_diff else "Diff not included (set include_diff=true to see full diff)",
            "truncated": truncated,
            "total_diff_lines": len(diff_lines) if include_diff else 0
        }
        
        return json.dumps(analysis, indent=2)
        
    except subprocess.CalledProcessError as e:
        return json.dumps({"error": f"Git error: {e.stderr}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    templates = [
        {
            "filename": filename,
            "type": template_type,
            "content": (TEMPLATES_DIR / filename).read_text()
        }
        for filename, template_type in DEFAULT_TEMPLATES.items()
    ]
    
    return json.dumps(templates, indent=2)


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.
    
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    
    # Get available templates
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)
    
    # Find matching template
    template_file = TYPE_MAPPING.get(change_type.lower(), "feature.md")
    selected_template = next(
        (t for t in templates if t["filename"] == template_file),
        templates[0]  # Default to first template if no match
    )
    
    suggestion = {
        "recommended_template": selected_template,
        "reasoning": f"Based on your analysis: '{changes_summary}', this appears to be a {change_type} change.",
        "template_content": selected_template["content"],
        "usage_hint": "Claude can help you fill out this template based on the specific changes in your PR."
    }
    
    return json.dumps(suggestion, indent=2)


# ===== Module 2: New GitHub Actions Tools =====

@mcp.tool()
async def get_recent_actions_events(limit: int = 10) -> str:
    """Get recent GitHub Actions events received via webhook.
    
    Args:
        limit: Maximum number of events to return (default: 10)
    """
    try:
        # Check if EVENTS_FILE exists
        if not EVENTS_FILE.exists():
            return json.dumps({"events": [], "message": "No events file found"})
        
        # Read the JSON file
        with open(EVENTS_FILE, 'r') as f:
            events = json.load(f)
        
        # Return the most recent events (up to limit)
        # Events are typically stored with most recent first, but let's ensure proper ordering
        if isinstance(events, list):
            recent_events = events[:limit]
        else:
            recent_events = []
        
        return json.dumps({
            "events": recent_events,
            "total_events": len(events) if isinstance(events, list) else 0,
            "showing": len(recent_events)
        }, indent=2)
        
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in events file: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": f"Error reading events: {str(e)}"})


@mcp.tool()
async def get_workflow_status(workflow_name: Optional[str] = None) -> str:
    """Get the current status of GitHub Actions workflows.
    
    Args:
        workflow_name: Optional specific workflow name to filter by
    """
    try:
        # Read events from EVENTS_FILE
        if not EVENTS_FILE.exists():
            return json.dumps({"workflows": {}, "message": "No events file found"})
        
        with open(EVENTS_FILE, 'r') as f:
            events = json.load(f)
        
        if not isinstance(events, list):
            return json.dumps({"workflows": {}, "message": "Invalid events format"})
        
        # Filter events for workflow_run events
        workflow_events = []
        for event in events:
            if isinstance(event, dict) and event.get('type') == 'workflow_run':
                workflow_events.append(event)
        
        # Group by workflow and show latest status
        workflows = {}
        for event in workflow_events:
            workflow_data = event.get('payload', {}).get('workflow_run', {})
            if not workflow_data:
                continue
                
            wf_name = workflow_data.get('name', 'Unknown')
            
            # If workflow_name provided, filter by that name
            if workflow_name and wf_name != workflow_name:
                continue
            
            # Track the most recent event for each workflow
            event_time = workflow_data.get('updated_at', workflow_data.get('created_at', ''))
            
            if wf_name not in workflows or event_time > workflows[wf_name].get('updated_at', ''):
                workflows[wf_name] = {
                    'name': wf_name,
                    'status': workflow_data.get('status', 'unknown'),
                    'conclusion': workflow_data.get('conclusion', None),
                    'updated_at': event_time,
                    'head_branch': workflow_data.get('head_branch', 'unknown'),
                    'html_url': workflow_data.get('html_url', ''),
                    'run_number': workflow_data.get('run_number', 0)
                }
        
        result = {
            "workflows": workflows,
            "total_workflows": len(workflows),
            "filtered_by": workflow_name if workflow_name else "all workflows"
        }
        
        return json.dumps(result, indent=2)
        
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in events file: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": f"Error reading workflow status: {str(e)}"})


# ===== Module 2: MCP Prompts =====

@mcp.prompt()
async def analyze_ci_results():
    """Analyze recent CI/CD results and provide insights."""
    return """You are a CI/CD analyst helping a development team understand their build and deployment pipeline health.

Please follow these steps to analyze the recent CI/CD results:

1. **Gather Recent Events**: Use get_recent_actions_events() to retrieve the latest GitHub Actions events (suggest using a limit of 20-30 events for comprehensive analysis).

2. **Get Workflow Status**: Use get_workflow_status() to get the current status of all workflows.

3. **Analyze the Data**: Look for patterns and insights including:
   - Overall success/failure rate of workflows
   - Most frequently failing workflows
   - Recent trends in build times or failure patterns
   - Any workflows that haven't run recently
   - Branch-specific issues (main vs feature branches)

4. **Provide Actionable Insights**: Based on your analysis, provide:
   - Summary of current CI/CD health
   - Identification of any problematic workflows or patterns
   - Recommendations for improvements
   - Priority issues that need immediate attention

5. **Format Your Response**: Present your findings in a clear, structured format with:
   - Executive summary (2-3 sentences)
   - Key metrics and statistics
   - Detailed findings with evidence
   - Recommended actions with priority levels

Focus on being data-driven and actionable in your analysis."""


@mcp.prompt()
async def create_deployment_summary():
    """Generate a deployment summary for team communication."""
    return """You are a technical communication specialist helping create clear, concise deployment summaries for cross-functional teams.

Please create a deployment summary by following these steps:

1. **Gather Current Data**:
   - Use get_recent_actions_events() to get recent deployment-related events
   - Use get_workflow_status() to check the status of deployment workflows
   - Use analyze_file_changes() to understand what code changes are being deployed

2. **Create Team-Friendly Summary**: Generate a deployment summary that includes:
   - **Deployment Status**: Current state (successful, in progress, failed, pending)
   - **What's Being Deployed**: High-level description of features/fixes (non-technical language)
   - **Timeline**: When the deployment started/completed or expected completion
   - **Impact**: What users or systems are affected
   - **Rollback Plan**: Brief mention of rollback status if needed

3. **Tailor for Audience**: Make the summary accessible to:
   - Product managers (focus on features and user impact)
   - Engineering teams (include technical details)
   - Support teams (highlight potential user-facing changes)
   - Leadership (focus on business impact and risks)

4. **Format Requirements**:
   - Use clear, jargon-free language
   - Include specific timestamps and version numbers
   - Use emoji or formatting for quick visual scanning
   - Keep the summary concise (under 200 words for executive summary)
   - Include links to relevant dashboards or monitoring

5. **Include Next Steps**: Clearly state what happens next and who is responsible for monitoring the deployment.

Focus on clarity, accuracy, and actionability for non-technical stakeholders."""


@mcp.prompt()
async def generate_pr_status_report():
    """Generate a comprehensive PR status report including CI/CD results."""
    return """You are a code review facilitator creating comprehensive pull request status reports that combine code analysis with CI/CD pipeline results.

Please generate a complete PR status report by following these steps:

1. **Analyze Code Changes**:
   - Use analyze_file_changes() to get detailed diff information
   - Identify the scope and type of changes (features, bugs, refactoring, etc.)
   - Note any significant architectural changes or dependencies

2. **Check CI/CD Pipeline Status**:
   - Use get_workflow_status() to get current workflow states
   - Use get_recent_actions_events() to see recent pipeline activity
   - Identify any failing or pending checks

3. **Generate Comprehensive Report** including:

   **📋 PR Overview**:
   - Summary of changes in 1-2 sentences
   - Files modified, lines added/removed
   - Type of change (feature, bugfix, etc.)

   **🔍 Code Analysis**:
   - Key changes and their purpose
   - Potential impact areas
   - Dependencies or breaking changes
   - Code quality observations

   **🚀 CI/CD Status**:
   - All workflow statuses (✅ passed, ❌ failed, ⏳ pending)
   - Any failing checks with details
   - Test coverage changes
   - Build/deployment status

   **🎯 Review Readiness**:
   - Is the PR ready for review? (all checks passing)
   - Any blockers or concerns
   - Recommended review focus areas
   - Merge readiness assessment

   **📈 Metrics & Stats**:
   - Build times
   - Test results summary
   - Performance impact (if available)

4. **Provide Actionable Recommendations**:
   - Next steps for the author
   - Specific areas for reviewers to focus on
   - Any required fixes before merge

Use clear formatting with sections, bullet points, and status indicators for easy scanning."""


@mcp.prompt()
async def troubleshoot_workflow_failure():
    """Help troubleshoot a failing GitHub Actions workflow."""
    return """You are a DevOps engineer specializing in GitHub Actions troubleshooting. Help systematically diagnose and resolve workflow failures.

Follow this structured troubleshooting approach:

1. **Initial Assessment**:
   - Use get_workflow_status() to identify which workflows are failing
   - Use get_recent_actions_events() to get recent failure events
   - Identify the specific workflow, job, and step that's failing

2. **Gather Failure Context**:
   - What type of failure is occurring? (build, test, deployment, etc.)
   - When did the failure start occurring?
   - Is this a new failure or recurring issue?
   - What changed recently? (code, dependencies, configuration)

3. **Systematic Diagnosis**:
   
   **🔍 Step 1 - Immediate Causes**:
   - Check error messages and logs from the failing step
   - Look for obvious issues (syntax errors, missing files, failed tests)
   - Verify environment variables and secrets are properly configured

   **🔍 Step 2 - Environmental Issues**:
   - Check if the issue is runner-specific (OS, versions)
   - Verify dependencies and package versions
   - Look for timeout issues or resource constraints

   **🔍 Step 3 - Recent Changes**:
   - Use analyze_file_changes() to see what code changed recently
   - Check if workflow files (.github/workflows/) were modified
   - Identify any dependency updates or configuration changes

   **🔍 Step 4 - Pattern Analysis**:
   - Is this failing on specific branches?
   - Does it fail consistently or intermittently?
   - Are related workflows also failing?

4. **Provide Solutions**:
   
   **🛠️ Immediate Actions** (quick fixes to try):
   - Specific steps to resolve the identified issue
   - Configuration changes needed
   - Code fixes required

   **🛠️ Prevention Measures** (avoid future occurrences):
   - Workflow improvements
   - Better error handling
   - Enhanced monitoring

5. **Create Action Plan**:
   - Prioritized list of steps to resolve the issue
   - Who should take each action
   - How to verify the fix worked
   - Monitoring to prevent recurrence

Be methodical, provide specific actionable steps, and explain the reasoning behind each recommendation."""


if __name__ == "__main__":
    print("Starting PR Agent MCP server...")
    print("NOTE: Run webhook_server.py in a separate terminal to receive GitHub events")
    mcp.run()