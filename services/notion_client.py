import logging
import requests
import json

logger = logging.getLogger(__name__)

def save_to_notion(draft, notion_api_key, page_id=None):
    """
    Save a draft to Notion either as a new page or update an existing one.
    
    Args:
        draft: Draft object to save
        notion_api_key: Notion API key
        page_id: Existing page ID to update (optional)
    
    Returns:
        page_id: ID of the created or updated page
    """
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # Format content blocks
    blocks = []
    
    # Convert the content to Notion blocks
    content_paragraphs = draft.content.split('\n\n')
    for paragraph in content_paragraphs:
        if paragraph.strip():
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": paragraph.strip()
                            }
                        }
                    ]
                }
            })
    
    if page_id:
        # Update existing page
        try:
            # Update the page title
            page_url = f"https://api.notion.com/v1/pages/{page_id}"
            page_data = {
                "properties": {
                    "title": {
                        "title": [
                            {
                                "text": {
                                    "content": draft.title
                                }
                            }
                        ]
                    }
                }
            }
            
            response = requests.patch(page_url, headers=headers, json=page_data)
            response.raise_for_status()
            
            # First delete existing content
            block_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
            response = requests.get(block_url, headers=headers)
            response.raise_for_status()
            existing_blocks = response.json().get('results', [])
            
            for block in existing_blocks:
                block_id = block.get('id')
                delete_url = f"https://api.notion.com/v1/blocks/{block_id}"
                requests.delete(delete_url, headers=headers)
            
            # Then add new content
            response = requests.patch(block_url, headers=headers, json={"children": blocks})
            response.raise_for_status()
            
            logger.info(f"Updated Notion page: {page_id}")
            return page_id
            
        except Exception as e:
            logger.error(f"Error updating Notion page: {str(e)}")
            raise
    else:
        # Create new page
        try:
            # Find or create a database to store the drafts
            database_id = find_or_create_database(notion_api_key)
            
            # Create the page in the database
            create_url = "https://api.notion.com/v1/pages"
            create_data = {
                "parent": {
                    "database_id": database_id
                },
                "properties": {
                    "title": {
                        "title": [
                            {
                                "text": {
                                    "content": draft.title
                                }
                            }
                        ]
                    }
                },
                "children": blocks
            }
            
            response = requests.post(create_url, headers=headers, json=create_data)
            response.raise_for_status()
            
            page_id = response.json().get('id')
            logger.info(f"Created Notion page: {page_id}")
            
            return page_id
            
        except Exception as e:
            logger.error(f"Error creating Notion page: {str(e)}")
            raise


def get_from_notion(page_id, notion_api_key):
    """
    Retrieve a draft from Notion
    
    Args:
        page_id: Notion page ID
        notion_api_key: Notion API key
    
    Returns:
        tuple: (title, content)
    """
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Notion-Version": "2022-06-28"
    }
    
    try:
        # Get page properties (title)
        page_url = f"https://api.notion.com/v1/pages/{page_id}"
        response = requests.get(page_url, headers=headers)
        response.raise_for_status()
        
        page_data = response.json()
        title = ""
        
        # Extract title from properties
        if 'properties' in page_data and 'title' in page_data['properties']:
            title_data = page_data['properties']['title']['title']
            if title_data:
                title = title_data[0]['plain_text']
        
        # Get page content (blocks)
        blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        response = requests.get(blocks_url, headers=headers)
        response.raise_for_status()
        
        blocks = response.json().get('results', [])
        content_parts = []
        
        # Extract text from blocks
        for block in blocks:
            block_type = block.get('type')
            if block_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item']:
                text_content = ""
                rich_text = block.get(block_type, {}).get('rich_text', [])
                
                for text_item in rich_text:
                    if text_item.get('type') == 'text':
                        text_content += text_item.get('text', {}).get('content', '')
                
                content_parts.append(text_content)
        
        content = "\n\n".join(content_parts)
        
        return title, content
        
    except Exception as e:
        logger.error(f"Error getting Notion page: {str(e)}")
        raise


def find_or_create_database(notion_api_key):
    """
    Find or create a database for storing drafts
    
    Args:
        notion_api_key: Notion API key
    
    Returns:
        database_id: ID of database
    """
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    try:
        # Search for existing database
        search_url = "https://api.notion.com/v1/search"
        search_data = {
            "filter": {
                "property": "object",
                "value": "database"
            },
            "query": "Newsletter Drafts"
        }
        
        response = requests.post(search_url, headers=headers, json=search_data)
        response.raise_for_status()
        
        results = response.json().get('results', [])
        
        # If database exists, return its ID
        for result in results:
            if result.get('object') == 'database' and 'title' in result:
                for title_item in result.get('title', []):
                    if 'text' in title_item and title_item.get('text', {}).get('content') == "Newsletter Drafts":
                        return result.get('id')
        
        # Otherwise, try to get the first workspace
        response = requests.post("https://api.notion.com/v1/search", headers=headers, json={"page_size": 1})
        response.raise_for_status()
        
        parent_id = None
        results = response.json().get('results', [])
        
        if results:
            parent_id = results[0].get('id')
        
        if not parent_id:
            raise Exception("Could not find a workspace to create the database in")
        
        # Create new database
        create_url = "https://api.notion.com/v1/databases"
        create_data = {
            "parent": {
                "type": "page_id",
                "page_id": parent_id
            },
            "title": [
                {
                    "type": "text",
                    "text": {
                        "content": "Newsletter Drafts"
                    }
                }
            ],
            "properties": {
                "title": {
                    "title": {}
                }
            }
        }
        
        response = requests.post(create_url, headers=headers, json=create_data)
        response.raise_for_status()
        
        database_id = response.json().get('id')
        logger.info(f"Created Notion database: {database_id}")
        
        return database_id
        
    except Exception as e:
        logger.error(f"Error finding or creating Notion database: {str(e)}")
        raise
