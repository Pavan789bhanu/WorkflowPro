"""
AI Service for natural language processing and workflow generation
Enhanced with video-based learning from demonstration videos
"""
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel
from app.automation.utils.logger import log


# Common app name to URL mappings - Canonical entry points for well-known apps
# Used for intent resolution, not hardcoding workflows
APP_URL_MAPPING = {
    # Project Management & Collaboration
    'linear': 'https://linear.app',
    'github': 'https://github.com',
    'gitlab': 'https://gitlab.com',
    'notion': 'https://notion.so',
    'asana': 'https://app.asana.com',
    'trello': 'https://trello.com',
    'jira': 'https://jira.atlassian.com',
    'slack': 'https://slack.com',
    'figma': 'https://figma.com',
    'miro': 'https://miro.com',
    'airtable': 'https://airtable.com',
    'monday': 'https://monday.com',
    'clickup': 'https://clickup.com',
    'basecamp': 'https://basecamp.com',
    'todoist': 'https://todoist.com',
    
    # Customer & Sales
    'zendesk': 'https://zendesk.com',
    'intercom': 'https://intercom.com',
    'hubspot': 'https://hubspot.com',
    'salesforce': 'https://salesforce.com',
    
    # E-commerce & Payments
    'stripe': 'https://stripe.com',
    'shopify': 'https://shopify.com',
    'wix': 'https://wix.com',
    'squarespace': 'https://squarespace.com',
    
    # Content & Publishing
    'wordpress': 'https://wordpress.com',
    'medium': 'https://medium.com',
    'substack': 'https://substack.com',
    'ghost': 'https://ghost.org',
    
    # Email & Marketing
    'mailchimp': 'https://mailchimp.com',
    'sendgrid': 'https://sendgrid.com',
    'gmail': 'https://mail.google.com',
    
    # Cloud & Infrastructure
    'aws': 'https://console.aws.amazon.com',
    'azure': 'https://portal.azure.com',
    'google cloud': 'https://console.cloud.google.com',
    'vercel': 'https://vercel.com',
    'netlify': 'https://netlify.com',
    'heroku': 'https://heroku.com',
    'digitalocean': 'https://digitalocean.com',
    
    # Storage & Documents
    'dropbox': 'https://dropbox.com',
    'google drive': 'https://drive.google.com',
    'google docs': 'https://docs.google.com',
    'google sheets': 'https://sheets.google.com',
    'onedrive': 'https://onedrive.live.com',
    
    # Communication
    'zoom': 'https://zoom.us',
    'teams': 'https://teams.microsoft.com',
    'discord': 'https://discord.com',
    
    # Social Media
    'twitter': 'https://twitter.com',
    'x': 'https://x.com',
    'linkedin': 'https://linkedin.com',
    'facebook': 'https://facebook.com',
    'instagram': 'https://instagram.com',
    'youtube': 'https://youtube.com',
    'tiktok': 'https://tiktok.com',
    'reddit': 'https://reddit.com',
    'pinterest': 'https://pinterest.com',
    
    # E-commerce
    'amazon': 'https://amazon.com',
    'ebay': 'https://ebay.com',
    'etsy': 'https://etsy.com',
}


class WorkflowAction(BaseModel):
    """Single workflow action"""
    type: str  # navigate, click, type, wait, select, etc.
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    timeout: Optional[int] = 5000
    description: str


class ParsedWorkflow(BaseModel):
    """Parsed workflow from natural language"""
    steps: List[WorkflowAction]
    confidence: float
    estimated_duration: int  # seconds
    requires_auth: bool
    warnings: List[str] = []


class AIService:
    """
    Service for AI-powered workflow generation
    
    Core Principles:
    - Extract web app name dynamically from user queries
    - Never hardcode URLs or assume specific products
    - Provide generic, adaptable instructions
    - Treat every app as variable, not constant
    """
    
    def __init__(self):
        # Provider-agnostic: any configured key (OpenAI or Anthropic) enables LLM parsing.
        from app.core.config import settings
        self.llm_available = settings.active_llm_provider != "none"
    
    def _infer_app_from_intent(self, description: str) -> Tuple[Optional[str], Optional[str], str]:
        """
        Autonomous AI function that infers the web application from natural language,
        even when not explicitly stated.
        
        This function bridges the gap between user intent and application identification.
        
        Examples:
        - "articles on Medium" → Medium
        - "Google document" → Google Docs
        - "create a document" → Google Docs (common default)
        - "summarize articles on drag" → Medium (content platform inference)
        
        Returns:
            Tuple of (app_name, canonical_url, reasoning)
        """
        description_lower = description.lower()
        
        # Pattern 1: Explicit app mention
        explicit_patterns = {
            # Content Platforms
            r'\bon\s+medium\b': ('Medium', 'https://medium.com', 'Explicitly mentioned'),
            r'\bmedium\s+article': ('Medium', 'https://medium.com', 'Platform mentioned with content type'),
            r'\bgoogle\s+doc': ('Google Docs', 'https://docs.google.com', 'Explicitly mentioned'),
            r'\bgoogle\s+sheet': ('Google Sheets', 'https://sheets.google.com', 'Explicitly mentioned'),
            r'\bgoogle\s+drive': ('Google Drive', 'https://drive.google.com', 'Explicitly mentioned'),
            r'\bnotion\s+page': ('Notion', 'https://notion.so', 'Platform mentioned with content type'),
            
            # Project Management
            r'\blinear\s+project': ('Linear', 'https://linear.app', 'Platform mentioned with object'),
            r'\basana\s+task': ('Asana', 'https://app.asana.com', 'Platform mentioned with object'),
            r'\btrello\s+board': ('Trello', 'https://trello.com', 'Platform mentioned with object'),
            r'\bjira\s+issue': ('Jira', 'https://jira.atlassian.com', 'Platform mentioned with object'),
            
            # Social Media
            r'\btwitter\s+post': ('Twitter', 'https://twitter.com', 'Platform mentioned'),
            r'\blinkedin\s+post': ('LinkedIn', 'https://linkedin.com', 'Platform mentioned'),
            r'\byoutube\s+video': ('YouTube', 'https://youtube.com', 'Platform mentioned'),
            
            # Communication
            r'\bslack\s+message': ('Slack', 'https://slack.com', 'Platform mentioned'),
            r'\bdiscord\s+server': ('Discord', 'https://discord.com', 'Platform mentioned'),
        }
        
        for pattern, (app, url, reason) in explicit_patterns.items():
            if re.search(pattern, description_lower):
                return (app, url, reason)
        
        # Pattern 2: Implicit inference from content type and action
        # "summarize articles" → Medium (common article platform)
        if 'article' in description_lower and ('summarize' in description_lower or 'read' in description_lower):
            if 'medium' in description_lower:
                return ('Medium', 'https://medium.com', 'Inferred from article context')
        
        # "create a document" → Google Docs (common default)
        if 'document' in description_lower and 'create' in description_lower:
            if 'google' in description_lower or not any(app in description_lower for app in ['notion', 'word']):
                return ('Google Docs', 'https://docs.google.com', 'Inferred from document creation intent')
        
        # "create a spreadsheet" → Google Sheets
        if 'spreadsheet' in description_lower or ('sheet' in description_lower and 'create' in description_lower):
            return ('Google Sheets', 'https://sheets.google.com', 'Inferred from spreadsheet intent')
        
        # "create a project" → Linear/Asana (project management default)
        if 'project' in description_lower and 'create' in description_lower:
            # Check for specific mentions
            if 'linear' in description_lower:
                return ('Linear', 'https://linear.app', 'Explicitly mentioned')
            elif 'asana' in description_lower:
                return ('Asana', 'https://app.asana.com', 'Explicitly mentioned')
            elif 'notion' in description_lower:
                return ('Notion', 'https://notion.so', 'Explicitly mentioned')
        
        # "search for" or "find" → Google (default search)
        if ('search' in description_lower or 'find' in description_lower) and 'google' not in description_lower:
            # Check if it's app-specific search
            for app_name, url in APP_URL_MAPPING.items():
                if app_name in description_lower:
                    return (app_name.title(), url, f'Search within {app_name}')
        
        # Pattern 3: Check for explicit app names in query
        for app_name, url in APP_URL_MAPPING.items():
            if app_name in description_lower:
                return (app_name.title(), url, 'App name found in query')
        
        # Pattern 4: No clear app identified
        return (None, None, 'Unable to identify app from context')
    
    def _decompose_intent(self, description: str) -> Dict[str, Any]:
        """
        Decompose user query into structured components for autonomous execution.
        
        Returns a dictionary with:
        - app_name: Identified or inferred web application
        - domain: Canonical domain
        - actions: Ordered list of operations
        - content: Text or topic to be processed
        - metadata: Names, titles, descriptions
        - object_type: What the user wants to work with (document, project, article, etc.)
        
        Example:
        "Create a Google document named My First Project and write about AI"
        →
        {
            'app_name': 'Google Docs',
            'domain': 'https://docs.google.com',
            'actions': ['create', 'rename', 'write'],
            'content': 'about AI',
            'metadata': {'name': 'My First Project'},
            'object_type': 'document'
        }
        """
        description_lower = description.lower()
        
        # Infer app from context
        app_name, domain, reasoning = self._infer_app_from_intent(description)
        
        # Extract actions
        actions = []
        action_keywords = {
            'create': ['create', 'new', 'make', 'add'],
            'search': ['search', 'find', 'look for', 'locate'],
            'summarize': ['summarize', 'summary', 'overview'],
            'write': ['write', 'compose', 'type', 'add text'],
            'rename': ['rename', 'name', 'call it', 'titled'],
            'open': ['open', 'access', 'go to'],
            'read': ['read', 'view', 'review'],
            'extract': ['extract', 'get', 'retrieve'],
            'login': ['login', 'sign in', 'authenticate'],
        }
        
        for action, keywords in action_keywords.items():
            if any(keyword in description_lower for keyword in keywords):
                actions.append(action)
        
        # Extract object type
        object_type = None
        object_keywords = {
            'document': ['document', 'doc'],
            'spreadsheet': ['spreadsheet', 'sheet'],
            'project': ['project'],
            'task': ['task'],
            'article': ['article', 'post', 'blog'],
            'page': ['page'],
            'meeting': ['meeting', 'event'],
            'board': ['board'],
            'issue': ['issue', 'ticket'],
        }
        
        for obj, keywords in object_keywords.items():
            if any(keyword in description_lower for keyword in keywords):
                object_type = obj
                break
        
        # Extract metadata (names, titles)
        metadata = {}
        
        # Pattern: "named X" or "called X" or "titled X"
        name_patterns = [
            r'named?\s+["\']?([^"\']+?)["\']?\s+(?:and|with|$)',
            r'called\s+["\']?([^"\']+?)["\']?\s+(?:and|with|$)',
            r'titled?\s+["\']?([^"\']+?)["\']?\s+(?:and|with|$)',
            r'name\s+(?:is|:)?\s*["\']?([^"\']+?)["\']?(?:\s|$)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                metadata['name'] = match.group(1).strip()
                break
        
        # Extract content/topic
        content = None
        content_patterns = [
            r'about\s+(.+?)(?:\s+and\s+|\s*$)',
            r'on\s+(.+?)(?:\s+and\s+|\s*$)',
            r'regarding\s+(.+?)(?:\s+and\s+|\s*$)',
            r'write\s+(.+?)(?:\s+and\s+|\s*$)',
        ]
        
        for pattern in content_patterns:
            match = re.search(pattern, description_lower)
            if match:
                content = match.group(1).strip()
                break
        
        return {
            'app_name': app_name,
            'domain': domain,
            'actions': actions,
            'content': content,
            'metadata': metadata,
            'object_type': object_type,
            'reasoning': reasoning,
            'original_query': description
        }
    
    def _extract_app_info(self, description: str) -> Tuple[Optional[str], Optional[str], str]:
        """
        Extract app name, URL, and enhanced description from user query
        
        Returns:
            Tuple of (app_name, app_url, enhanced_description)
        """
        description_lower = description.lower()
        
        # Pattern matching for common phrases
        patterns = [
            r'\bin\s+(\w+)',      # "in Linear"
            r'\bon\s+(\w+)',      # "on GitHub"
            r'\busing\s+(\w+)',   # "using Notion"
            r'\bwith\s+(\w+)',    # "with Asana"
            r'\bfor\s+(\w+)',     # "for Jira"
        ]
        
        app_name = None
        app_url = None
        
        # Try to match app name from patterns
        for pattern in patterns:
            match = re.search(pattern, description_lower)
            if match:
                potential_app = match.group(1).lower()
                # Check if it's in our mapping
                if potential_app in APP_URL_MAPPING:
                    app_name = potential_app.capitalize()
                    app_url = APP_URL_MAPPING[potential_app]
                    break
        
        # Enhance description if app was found
        enhanced_description = self._enhance_description(description, app_name) if app_name else description
        
        return app_name, app_url, enhanced_description
    
    def _extract_url_from_query(self, description: str) -> Optional[str]:
        """
        Extract URL from user query using intelligent methods WITHOUT hardcoding.
        
        Priority:
        1. Direct URL in query (e.g., "login to https://myapp.com")
        2. Domain extraction (e.g., "login to myapp.com")
        3. App name mapping (only as convenience, not assumption)
        
        Returns:
            Extracted URL or None
        """
        description_lower = description.lower()
        
        # Method 1: Direct URL extraction (HIGHEST PRIORITY)
        url_pattern = r'https?://[^\s]+'
        url_match = re.search(url_pattern, description)
        if url_match:
            url = url_match.group(0).rstrip('.,;!?)')
            return url
        
        # Method 2: Extract domain-like pattern (e.g., "myapp.com", "app.company.io")
        # This works for ANY domain without hardcoding
        domain_pattern = r'\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)\b'
        domain_match = re.search(domain_pattern, description)
        if domain_match:
            domain = domain_match.group(1)
            return f"https://{domain}"
        
        # Method 3: Extract app name and ONLY map if it exists in common list
        # This is convenience, not hardcoding - user explicitly mentioned the app
        patterns = [
            r'\bin\s+(\w+)',
            r'\bon\s+(\w+)',
            r'\bto\s+(\w+)',
            r'\busing\s+(\w+)',
            r'\bwith\s+(\w+)',
            r'\bfor\s+(\w+)',
            r'\bat\s+(\w+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description_lower)
            if match:
                app_name = match.group(1).lower()
                # Only use mapping if app is in our convenience list
                # This helps UX but doesn't restrict functionality
                if app_name in APP_URL_MAPPING:
                    return APP_URL_MAPPING[app_name]
        
        # If no URL found, return None
        # The system will use target_url or prompt user to provide URL
        return None
    
    def _extract_app_name_generic(self, description: str, url: str) -> Optional[str]:
        """
        Extract app name from description or URL dynamically.
        Never assumes or hardcodes - extracts what the user mentioned.
        
        Returns:
            App name mentioned by user or derived from URL
        """
        # Try to extract app name explicitly mentioned in description
        # Look for capitalized words after prepositions (indicates proper nouns)
        patterns = [
            r'\bin\s+([A-Z][a-zA-Z]+)',      # "in Notion"
            r'\bon\s+([A-Z][a-zA-Z]+)',      # "on GitHub"
            r'\bto\s+([A-Z][a-zA-Z]+)',      # "to Asana"
            r'\busing\s+([A-Z][a-zA-Z]+)',   # "using Trello"
            r'\bwith\s+([A-Z][a-zA-Z]+)',    # "with Jira"
            r'\bfor\s+([A-Z][a-zA-Z]+)',     # "for Monday"
            r'\bat\s+([A-Z][a-zA-Z]+)',      # "at Slack"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                return match.group(1)
        
        # If no explicit app name in description, extract from URL
        if url and url != "https://example.com":
            # Parse domain from URL
            domain_match = re.search(r'https?://(?:www\.)?([^/.]+)', url)
            if domain_match:
                domain = domain_match.group(1)
                # Extract first part as app name (e.g., "myapp" from "myapp.com")
                app_name = domain.split('.')[0]
                return app_name.capitalize()
        
        # If still no app name found, return None
        # This is intentional - we don't assume or hardcode
        return None
    
    def _generate_generic_context(self, description: str) -> Dict[str, Any]:
        """
        Generate generic project context from description
        
        Returns:
            Dictionary with project_name, project_description, tags, priority
        """
        # Extract action from description
        description_lower = description.lower()
        
        # Generate project name
        if "create" in description_lower and "project" in description_lower:
            project_name = "Automated Project"
        else:
            # Use first few words as project name
            words = description.split()[:3]
            project_name = " ".join(words).title()
        
        # Generate description
        project_description = f"Automated task: {description}"
        
        # Extract tags
        tags = []
        if "project" in description_lower:
            tags.append("project-management")
        if "login" in description_lower or "auth" in description_lower:
            tags.append("authentication")
        if "search" in description_lower:
            tags.append("search")
        if "data" in description_lower or "extract" in description_lower:
            tags.append("data")
        if not tags:
            tags.append("automation")
        
        return {
            'project_name': project_name,
            'project_description': project_description,
            'tags': tags[:3],
            'priority': 'medium'
        }
        
    def _enhance_description(self, original_description: str, app_name: Optional[str]) -> str:
        """
        Generate detailed, professional description from user query
        """
        description_lower = original_description.lower()
        
        # Extract action intent
        action_keywords = {
            'create': 'Creates',
            'add': 'Adds',
            'update': 'Updates',
            'delete': 'Deletes',
            'login': 'Authenticates to',
            'sign in': 'Signs into',
            'search': 'Searches within',
            'scrape': 'Extracts data from',
            'fill': 'Completes form on',
            'submit': 'Submits data to',
            'download': 'Downloads from',
            'upload': 'Uploads to',
        }
        
        action_verb = 'Automates'
        for keyword, verb in action_keywords.items():
            if keyword in description_lower:
                action_verb = verb
                break
        
        # Build enhanced description
        if app_name:
            enhanced = f"{action_verb} {app_name} - {original_description}"
        else:
            enhanced = f"{action_verb} workflow: {original_description}"
        
        # Add project context if creating something
        if 'create' in description_lower or 'add' in description_lower:
            if 'project' in description_lower:
                enhanced += " | Includes project setup with name, description, and initial configuration"
            elif 'task' in description_lower or 'issue' in description_lower:
                enhanced += " | Sets up task with title, description, and relevant labels"
            elif 'form' in description_lower:
                enhanced += " | Fills form fields with appropriate data and validation"
        
        return enhanced
    
    def _extract_tags(self, description: str) -> List[str]:
        """Extract relevant tags from description"""
        tags = []
        
        tag_keywords = {
            'automation': ['automat', 'workflow', 'task'],
            'development': ['dev', 'code', 'programming', 'github', 'gitlab'],
            'project-management': ['project', 'task', 'issue', 'linear', 'jira', 'asana'],
            'data': ['data', 'scrape', 'extract', 'collect'],
            'testing': ['test', 'qa', 'quality'],
            'documentation': ['doc', 'document', 'wiki', 'notion'],
        }
        
        for tag, keywords in tag_keywords.items():
            if any(keyword in description for keyword in keywords):
                tags.append(tag)
        
        return tags[:3]  # Limit to 3 most relevant tags
        
    async def parse_task_description(
        self, 
        description: str, 
        target_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ParsedWorkflow:
        """
        Parse natural language task description into workflow steps.
        Uses the configured LLM provider (OpenAI or Anthropic), falling back
        to rule-based parsing when no provider is available.
        """
        if self.llm_available:
            try:
                return await self._call_llm_parse(description, target_url, context)
            except Exception as e:
                log(f"[AI Service] LLM call failed: {e}, falling back to rule-based parser", level="warning")

        return self._mock_parse(description, target_url)

    async def _call_llm_parse(
        self,
        description: str,
        target_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ParsedWorkflow:
        """Call the configured LLM to convert a task into executable workflow steps."""
        from app.services.llm_client import get_llm_client

        system_prompt = """You are an expert browser automation assistant. Convert natural language task descriptions into precise, executable browser automation workflows.

Return ONLY a valid JSON object (no markdown, no extra text) with this exact structure:
{
  "steps": [
    {
      "type": "navigate",
      "url": "https://example.com",
      "selector": null,
      "value": null,
      "timeout": 5000,
      "description": "Navigate to the website"
    }
  ],
  "confidence": 0.85,
  "estimated_duration": 30,
  "requires_auth": false,
  "warnings": []
}

Step types available:
- "navigate": Go to a URL. Requires "url" field.
- "click": Click an element. Requires "selector" field.
- "type": Type text into an input. Requires "selector" and "value" fields. Clear the field first.
- "wait": Wait for an element or a duration. Use "selector" for element wait, "timeout" (ms) for time wait.
- "select": Choose a dropdown option. Requires "selector" and "value".
- "extract": Extract text content. Requires "selector".
- "screenshot": Capture a screenshot. No extra fields needed.

Selector best practices:
- Prefer semantic: [data-testid="..."], [aria-label="..."], input[name="..."]
- Text-based for buttons: button:has-text("Submit"), a:has-text("Login")
- Type-based for inputs: input[type="email"], input[type="password"], input[type="search"]
- Avoid fragile class-based or deeply nested selectors

Workflow best practices:
- Always start with a navigate step.
- Add a wait step after navigation to let dynamic content load.
- After clicking a button that opens a form or modal, add a short wait.
- Set requires_auth=true when login credentials are needed.
- Set confidence 0.9+ when the task is very specific, 0.6-0.8 for general tasks.
- Add warnings for tasks that require credentials, could have side effects, or are ambiguous."""

        user_message = f"Task: {description}"
        if target_url:
            user_message += f"\nTarget URL: {target_url}"
        if context:
            user_message += f"\nContext: {json.dumps(context, indent=2)}"

        result = await get_llm_client().chat_json(
            messages=[{"role": "user", "content": user_message}],
            system=system_prompt,
            temperature=0.2,
            max_tokens=2000,
        )

        steps = []
        for step_data in result.get("steps", []):
            try:
                steps.append(WorkflowAction(**step_data))
            except Exception:
                pass

        return ParsedWorkflow(
            steps=steps,
            confidence=float(result.get("confidence", 0.8)),
            estimated_duration=int(result.get("estimated_duration", len(steps) * 3)),
            requires_auth=bool(result.get("requires_auth", False)),
            warnings=result.get("warnings", []),
        )
    
    def _mock_parse(self, description: str, target_url: Optional[str]) -> ParsedWorkflow:
        """
        Autonomous AI workflow parser that:
        1. Identifies web application from natural language (implicit or explicit)
        2. Decomposes user intent into structured actions
        3. Generates end-to-end executable workflow
        4. Handles navigation, authentication, and task completion
        
        This is the bridge between "user thinks in goals" and "system executes in apps".
        """
        # Step 1: Decompose intent to identify app and actions
        intent = self._decompose_intent(description)
        
        # Step 2: Determine base URL
        if target_url:
            base_url = target_url
            app_name = self._extract_app_name_generic(description, base_url)
        elif intent['domain']:
            base_url = intent['domain']
            app_name = intent['app_name']
        else:
            # Fallback: try to extract from description
            extracted_url = self._extract_url_from_query(description)
            base_url = extracted_url or "https://example.com"
            app_name = self._extract_app_name_generic(description, base_url)
        
        # Step 3: Generate context
        project_context = self._generate_generic_context(description)
        
        # Override with extracted metadata if available
        if intent['metadata'].get('name'):
            project_context['project_name'] = intent['metadata']['name']
        if intent['content']:
            project_context['project_description'] = intent['content']
        
        steps = []
        
        # Step 4: Generate workflow based on decomposed intent
        primary_action = intent['actions'][0] if intent['actions'] else 'navigate'
        object_type = intent['object_type']
        
        # AUTONOMOUS WORKFLOW GENERATION
        # Based on: app + action + object_type + content
        
        if primary_action == 'create' and object_type == 'document':
            # Workflow: Create document (Google Docs, Notion, etc.)
            steps.extend(self._generate_create_document_workflow(
                base_url, app_name, intent
            ))
        
        elif primary_action == 'create' and object_type in ['project', 'task']:
            # Workflow: Create project/task
            steps.extend(self._generate_create_project_workflow(
                base_url, app_name, intent
            ))
        
        elif primary_action == 'summarize' and object_type == 'article':
            # Workflow: Search and summarize articles
            steps.extend(self._generate_summarize_articles_workflow(
                base_url, app_name, intent
            ))
        
        elif primary_action in ['search', 'find']:
            # Workflow: Search for content
            steps.extend(self._generate_search_workflow(
                base_url, app_name, intent
            ))
        
        elif primary_action == 'login':
            # Workflow: Authentication
            steps.extend(self._generate_login_workflow(
                base_url, app_name, intent
            ))
        
        else:
            # Fallback: Generic navigation + action
            steps.extend(self._generate_generic_workflow(
                base_url, app_name, intent
            ))
        
        # Add final stabilization
        if steps and steps[-1].type != "wait":
            steps.append(
                WorkflowAction(
                    type="wait",
                    timeout=1000,
                    description="Wait for final state to stabilize"
                )
            )
        
        # Generate contextual warnings
        warnings = self._generate_contextual_warnings(intent, app_name)
        
        return ParsedWorkflow(
            steps=steps,
            confidence=0.85 if intent['app_name'] else 0.70,
            estimated_duration=len(steps) * 3,
            requires_auth='login' in intent['actions'],
            warnings=warnings
        )

    def _generate_create_document_workflow(self, base_url: str, app_name: Optional[str], intent: Dict) -> List[WorkflowAction]:
        """
        Generate workflow for creating a document (Google Docs, Notion, etc.)
        Example: "Create a Google document named My First Project and write about AI"
        """
        steps = []
        doc_name = intent['metadata'].get('name', 'Untitled Document')
        content = intent['content'] or 'Document content'
        
        steps.extend([
            WorkflowAction(
                type="navigate",
                url=base_url,
                description=f"Navigate to {app_name or 'document platform'} homepage"
            ),
            WorkflowAction(
                type="wait",
                selector="body, [role='main']",
                timeout=3000,
                description="Wait for page to load"
            ),
            WorkflowAction(
                type="click",
                selector="button:has-text('New'), a:has-text('Create'), button:has-text('Blank'), [aria-label*='New document'], [aria-label*='Create']",
                description="Click 'New Document' or 'Create' button"
            ),
            WorkflowAction(
                type="wait",
                timeout=2000,
                description="Wait for document editor to load"
            ),
            WorkflowAction(
                type="click",
                selector="h1, [contenteditable='true'], [role='textbox'], input[placeholder*='title' i], input[placeholder*='name' i]",
                description="Click on document title field"
            ),
            WorkflowAction(
                type="type",
                selector="h1, [contenteditable='true']:first, input[placeholder*='title' i]",
                value=doc_name,
                description=f"Enter document name: '{doc_name}'"
            ),
            WorkflowAction(
                type="click",
                selector="[role='textbox'], [contenteditable='true']:not(h1), .doc-content, p",
                description="Click in document body"
            ),
            WorkflowAction(
                type="type",
                selector="[role='textbox'], [contenteditable='true']:not(h1)",
                value=content,
                description=f"Write content: '{content}'"
            ),
            WorkflowAction(
                type="wait",
                timeout=2000,
                description="Wait for auto-save to complete"
            )
        ])
        
        return steps
    
    def _generate_create_project_workflow(self, base_url: str, app_name: Optional[str], intent: Dict) -> List[WorkflowAction]:
        """
        Generate workflow for creating a project/task
        Example: "Create a project in Linear named Q1 Planning"
        """
        steps = []
        project_name = intent['metadata'].get('name', 'New Project')
        description = intent['content'] or 'Project description'
        
        steps.extend([
            WorkflowAction(
                type="navigate",
                url=base_url,
                description=f"Navigate to {app_name or 'project management platform'}"
            ),
            WorkflowAction(
                type="wait",
                selector="body, [role='main']",
                timeout=3000,
                description="Wait for dashboard to load"
            ),
            WorkflowAction(
                type="click",
                selector="button:has-text('New Project'), button:has-text('Create'), button:has-text('Add'), [aria-label*='Create'], [aria-label*='New']",
                description="Click 'New Project' or 'Create' button"
            ),
            WorkflowAction(
                type="wait",
                timeout=1500,
                description="Wait for creation form"
            ),
            WorkflowAction(
                type="type",
                selector="input[name='name'], input[name='title'], input[placeholder*='name' i], input[type='text']:first",
                value=project_name,
                description=f"Enter project name: '{project_name}'"
            ),
            WorkflowAction(
                type="type",
                selector="textarea[name='description'], textarea[placeholder*='description' i], input[name='description']",
                value=description,
                description=f"Enter project description: '{description}'"
            ),
            WorkflowAction(
                type="click",
                selector="button[type='submit'], button:has-text('Create'), button:has-text('Save'), [aria-label*='Create']",
                description="Submit project creation"
            ),
            WorkflowAction(
                type="wait",
                timeout=2000,
                description="Wait for project to be created"
            )
        ])
        
        return steps
    
    def _generate_summarize_articles_workflow(self, base_url: str, app_name: Optional[str], intent: Dict) -> List[WorkflowAction]:
        """
        Generate workflow for searching and summarizing articles
        Example: "Summarize articles on RAG in Medium"
        """
        steps = []
        search_topic = intent['content'] or 'topic'
        
        steps.extend([
            WorkflowAction(
                type="navigate",
                url=base_url,
                description=f"Navigate to {app_name or 'content platform'}"
            ),
            WorkflowAction(
                type="wait",
                selector="input[type='search'], input[name='q'], [role='searchbox']",
                timeout=3000,
                description="Wait for homepage to load"
            ),
            WorkflowAction(
                type="click",
                selector="input[type='search'], input[name='q'], [placeholder*='Search' i], [role='searchbox']",
                description="Click on search bar"
            ),
            WorkflowAction(
                type="type",
                selector="input[type='search'], input[name='q'], [role='searchbox']",
                value=search_topic,
                description=f"Enter search query: '{search_topic}'"
            ),
            WorkflowAction(
                type="click",
                selector="button[type='submit'], button:has-text('Search'), [aria-label*='Search']",
                description="Submit search"
            ),
            WorkflowAction(
                type="wait",
                timeout=3000,
                description="Wait for search results to load"
            ),
            WorkflowAction(
                type="extract",
                selector="article, .post, .story, [role='article']",
                description="Extract article titles and previews for summarization"
            ),
            WorkflowAction(
                type="click",
                selector="article:first-of-type a, .post:first a, .story:first a",
                description="Open first relevant article"
            ),
            WorkflowAction(
                type="wait",
                timeout=2000,
                description="Wait for article to load"
            ),
            WorkflowAction(
                type="extract",
                selector="article, [role='article'], .article-content, main",
                description="Extract article content for summarization"
            )
        ])
        
        return steps
    
    def _generate_search_workflow(self, base_url: str, app_name: Optional[str], intent: Dict) -> List[WorkflowAction]:
        """Generate generic search workflow"""
        steps = []
        search_query = intent['content'] or '{{SEARCH_QUERY}}'
        
        steps.extend([
            WorkflowAction(
                type="navigate",
                url=base_url,
                description=f"Navigate to {app_name or 'website'}"
            ),
            WorkflowAction(
                type="wait",
                selector="input[type='search'], input[name='q'], [role='searchbox']",
                timeout=3000,
                description="Wait for page to load"
            ),
            WorkflowAction(
                type="click",
                selector="input[type='search'], input[name='q'], [placeholder*='Search' i], [role='searchbox']",
                description="Focus search input"
            ),
            WorkflowAction(
                type="type",
                selector="input[type='search'], input[name='q'], [role='searchbox']",
                value=search_query,
                description="Enter search query"
            ),
            WorkflowAction(
                type="click",
                selector="button[type='submit'], button[aria-label*='Search'], button:has-text('Search')",
                description="Submit search"
            ),
            WorkflowAction(
                type="wait",
                timeout=3000,
                description="Wait for search results"
            )
        ])
        
        return steps
    
    def _generate_login_workflow(self, base_url: str, app_name: Optional[str], intent: Dict) -> List[WorkflowAction]:
        """Generate authentication workflow"""
        steps = []
        
        steps.extend([
            WorkflowAction(
                type="navigate",
                url=f"{base_url}/login" if not base_url.endswith('/login') else base_url,
                description=f"Navigate to {app_name or 'application'} login page"
            ),
            WorkflowAction(
                type="wait",
                selector="input[type='email'], input[name='email'], input[autocomplete='username']",
                timeout=3000,
                description="Wait for login form"
            ),
            WorkflowAction(
                type="type",
                selector="input[name='email'], input[type='email'], input[autocomplete='username']",
                value="user@example.com",
                description="Enter email or username"
            ),
            WorkflowAction(
                type="type",
                selector="input[name='password'], input[type='password']",
                value="{{PASSWORD}}",
                description="Enter password (use secure credential management)"
            ),
            WorkflowAction(
                type="click",
                selector="button[type='submit'], button:has-text('Login'), button:has-text('Sign in')",
                description="Click login button"
            ),
            WorkflowAction(
                type="wait",
                timeout=3000,
                description="Wait for authentication"
            )
        ])
        
        return steps
    
    def _generate_generic_workflow(self, base_url: str, app_name: Optional[str], intent: Dict) -> List[WorkflowAction]:
        """Generate fallback generic workflow"""
        return [
            WorkflowAction(
                type="navigate",
                url=base_url,
                description=f"Navigate to {app_name or 'web application'}"
            ),
            WorkflowAction(
                type="wait",
                selector="body, [role='main']",
                timeout=3000,
                description="Wait for page to load"
            )
        ]
    
    def _generate_contextual_warnings(self, intent: Dict, app_name: Optional[str]) -> List[str]:
        """Generate contextual warnings based on intent"""
        warnings = []
        
        if app_name:
            warnings.append(f"🎯 Identified Application: {app_name}")
        else:
            warnings.append("⚠️ Application could not be identified. Please provide more context.")
        
        if intent['reasoning']:
            warnings.append(f"💡 Reasoning: {intent['reasoning']}")
        
        warnings.append("📋 Review the generated workflow and test before production use.")
        
        if intent['metadata'].get('name'):
            warnings.append(f"📝 Name/Title: '{intent['metadata']['name']}'")
        
        if intent['content']:
            warnings.append(f"📄 Content/Topic: '{intent['content'][:50]}...'")
        
        if 'login' in intent['actions']:
            warnings.append("🔐 Requires authentication. Ensure credentials are configured.")
        
        return warnings
    
    async def suggest_next_actions(
        self,
        current_steps: List[Dict[str, Any]],
        page_context: Optional[Dict[str, Any]] = None
    ) -> List[WorkflowAction]:
        """
        Suggest next possible actions based on current workflow state
        
        Args:
            current_steps: List of steps already in workflow
            page_context: Current page state/context
            
        Returns:
            List of suggested next actions
        """
        # TODO: Implement with LLM
        suggestions = []
        
        if not current_steps:
            suggestions.append(
                WorkflowAction(
                    type="navigate",
                    url="https://",
                    description="Navigate to a website"
                )
            )
        else:
            last_step = current_steps[-1]
            
            if last_step.get("type") == "navigate":
                suggestions.extend([
                    WorkflowAction(
                        type="wait",
                        selector=".content, main",
                        description="Wait for page to load"
                    ),
                    WorkflowAction(
                        type="click",
                        selector="",
                        description="Click an element"
                    )
                ])
            elif last_step.get("type") == "click":
                suggestions.extend([
                    WorkflowAction(
                        type="type",
                        selector="input",
                        description="Type into an input field"
                    ),
                    WorkflowAction(
                        type="wait",
                        timeout=1000,
                        description="Wait for response"
                    )
                ])
        
        return suggestions
    
    async def validate_workflow(
        self,
        workflow_steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate workflow for common issues
        
        Args:
            workflow_steps: List of workflow steps
            
        Returns:
            Validation result with issues and suggestions
        """
        issues = []
        suggestions = []
        
        # Check for common issues
        if not workflow_steps:
            issues.append({
                "severity": "error",
                "message": "Workflow has no steps"
            })
        
        # Check first step is navigation
        if workflow_steps and workflow_steps[0].get("type") != "navigate":
            issues.append({
                "severity": "warning",
                "message": "Workflow should typically start with a navigation step"
            })
            suggestions.append("Add a navigate step at the beginning")
        
        # Check for missing selectors
        for i, step in enumerate(workflow_steps):
            if step.get("type") in ["click", "type", "select"] and not step.get("selector"):
                issues.append({
                    "severity": "error",
                    "message": f"Step {i+1}: Missing selector for {step.get('type')} action"
                })
        
        # Check for very long workflows
        if len(workflow_steps) > 20:
            issues.append({
                "severity": "warning",
                "message": "Workflow has many steps. Consider breaking into smaller workflows."
            })
        
        return {
            "valid": len([i for i in issues if i["severity"] == "error"]) == 0,
            "issues": issues,
            "suggestions": suggestions
        }
    
    async def optimize_workflow(
        self,
        workflow_steps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Optimize workflow by removing redundant steps, adding waits, etc.
        
        Args:
            workflow_steps: Original workflow steps
            
        Returns:
            Optimized workflow steps
        """
        optimized = []
        
        for i, step in enumerate(workflow_steps):
            # Add wait after navigation
            if step.get("type") == "navigate" and i < len(workflow_steps) - 1:
                next_step = workflow_steps[i + 1]
                if next_step.get("type") != "wait":
                    optimized.append(step)
                    optimized.append({
                        "type": "wait",
                        "timeout": 2000,
                        "description": "Wait for page to load"
                    })
                    continue
            
            # Skip duplicate waits
            if step.get("type") == "wait" and optimized and optimized[-1].get("type") == "wait":
                continue
                
            optimized.append(step)
        
        return optimized


# Singleton instance
ai_service = AIService()
