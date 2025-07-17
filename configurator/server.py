#!/usr/bin/env python3
"""
HiFiBerry Configuration API Server

A REST API server that provides access to the HiFiBerry configuration database
and other system configuration services.
"""

import os
import sys
import json
import logging
import argparse
from flask import Flask, request, jsonify, make_response
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError
from typing import Dict, Any, Optional

# Import the ConfigDB class
from .configdb import ConfigDB

# Set up logging
logger = logging.getLogger(__name__)

class ConfigAPIServer:
    """REST API server for HiFiBerry configuration services"""
    
    def __init__(self, host='0.0.0.0', port=1081, debug=False):
        """
        Initialize the API server
        
        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to listen on (default: 1081)
            debug: Enable debug mode
        """
        self.host = host
        self.port = port
        self.debug = debug
        self.app = Flask(__name__)
        self.configdb = ConfigDB()
        
        # Configure Flask logging
        if not debug:
            self.app.logger.setLevel(logging.WARNING)
        
        # Register API routes
        self._register_routes()
    
    def _get_html_documentation(self):
        """Generate HTML documentation for browser viewing"""
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HiFiBerry Configuration API Documentation</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        h3 {{ color: #7f8c8d; }}
        .endpoint {{ background: #ecf0f1; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #3498db; }}
        .method {{ display: inline-block; padding: 3px 8px; border-radius: 3px; font-weight: bold; font-size: 12px; }}
        .get {{ background: #27ae60; color: white; }}
        .post {{ background: #f39c12; color: white; }}
        .put {{ background: #e67e22; color: white; }}
        .delete {{ background: #e74c3c; color: white; }}
        .code {{ background: #2c3e50; color: #ecf0f1; padding: 10px; border-radius: 4px; overflow-x: auto; font-family: 'Courier New', monospace; }}
        .param {{ background: #f8f9fa; padding: 5px; margin: 5px 0; border-radius: 3px; }}
        .param-name {{ font-weight: bold; color: #e74c3c; }}
        .example {{ background: #f8f9fa; padding: 10px; border-radius: 4px; margin: 10px 0; }}
        .response {{ background: #d5f4e6; padding: 10px; border-radius: 4px; margin: 10px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .nav {{ background: #34495e; color: white; padding: 15px; margin: -30px -30px 30px -30px; border-radius: 8px 8px 0 0; }}
        .nav a {{ color: #3498db; text-decoration: none; margin-right: 20px; }}
        .nav a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <h1 style="margin: 0; border: none; padding: 0;">HiFiBerry Configuration API v1.7.0</h1>
            <p style="margin: 5px 0 0 0;">
                <a href="#endpoints">Endpoints</a>
                <a href="#examples">Examples</a>
                <a href="#errors">Error Codes</a>
                <a href="/api/v1/openapi.json">OpenAPI Spec</a>
            </p>
        </div>
        
        <h2>Overview</h2>
        <p>The HiFiBerry Configuration API provides REST endpoints for managing configuration settings in the HiFiBerry system. 
        All responses are in JSON format with consistent structure.</p>
        
        <p><strong>Base URL:</strong> <code>http://{self.host}:{self.port}</code></p>
        
        <h2 id="endpoints">API Endpoints</h2>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span> /health</h3>
            <p>Health check endpoint to verify the API server is running.</p>
            <div class="response">
                <strong>Response:</strong>
                <pre class="code">{{"status": "healthy", "service": "hifiberry-config-api", "version": "1.6.8"}}</pre>
            </div>
        </div>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span> /api/v1/config</h3>
            <p>Get all configuration key-value pairs.</p>
            <div class="param">
                <span class="param-name">prefix</span> (query, optional): Filter keys by prefix
            </div>
            <div class="response">
                <strong>Response:</strong>
                <pre class="code">{{"status": "success", "data": {{"volume": "75", "soundcard": "hifiberry-dac"}}, "count": 2}}</pre>
            </div>
        </div>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span> /api/v1/config/keys</h3>
            <p>Get all configuration keys only (without values).</p>
            <div class="param">
                <span class="param-name">prefix</span> (query, optional): Filter keys by prefix
            </div>
            <div class="response">
                <strong>Response:</strong>
                <pre class="code">{{"status": "success", "data": ["volume", "soundcard"], "count": 2}}</pre>
            </div>
        </div>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span> /api/v1/config/{{key}}</h3>
            <p>Get a specific configuration value by key.</p>
            <div class="param">
                <span class="param-name">key</span> (path, required): Configuration key name
            </div>
            <div class="param">
                <span class="param-name">secure</span> (query, optional): Set to "true" for secure/encrypted values
            </div>
            <div class="param">
                <span class="param-name">default</span> (query, optional): Default value if key not found
            </div>
            <div class="response">
                <strong>Response:</strong>
                <pre class="code">{{"status": "success", "data": {{"key": "volume", "value": "75"}}}}</pre>
            </div>
        </div>
        
        <div class="endpoint">
            <h3><span class="method post">POST</span> / <span class="method put">PUT</span> /api/v1/config/{{key}}</h3>
            <p>Set or update a configuration value.</p>
            <div class="param">
                <span class="param-name">key</span> (path, required): Configuration key name
            </div>
            <div class="param">
                <span class="param-name">Content-Type</span> (header, required): application/json
            </div>
            <div class="param">
                <strong>Request Body:</strong><br>
                <span class="param-name">value</span> (required): The value to set<br>
                <span class="param-name">secure</span> (optional): Store as encrypted value
            </div>
            <div class="example">
                <strong>Request Body Example:</strong>
                <pre class="code">{{"value": "75", "secure": false}}</pre>
            </div>
            <div class="response">
                <strong>Response:</strong>
                <pre class="code">{{"status": "success", "message": "Configuration key \\"volume\\" set successfully", "data": {{"key": "volume", "value": "75"}}}}</pre>
            </div>
        </div>
        
        <div class="endpoint">
            <h3><span class="method delete">DELETE</span> /api/v1/config/{{key}}</h3>
            <p>Delete a configuration key and its value.</p>
            <div class="param">
                <span class="param-name">key</span> (path, required): Configuration key name
            </div>
            <div class="response">
                <strong>Response:</strong>
                <pre class="code">{{"status": "success", "message": "Configuration key \\"volume\\" deleted successfully"}}</pre>
            </div>
        </div>
        
        <h2 id="examples">Usage Examples</h2>
        
        <h3>curl Commands</h3>
        <div class="example">
            <strong>Get all configuration:</strong>
            <pre class="code">curl http://{self.host}:{self.port}/api/v1/config</pre>
        </div>
        
        <div class="example">
            <strong>Get specific value:</strong>
            <pre class="code">curl http://{self.host}:{self.port}/api/v1/config/volume</pre>
        </div>
        
        <div class="example">
            <strong>Set configuration value:</strong>
            <pre class="code">curl -X POST -H "Content-Type: application/json" \\
     -d '{{"value":"75"}}' \\
     http://{self.host}:{self.port}/api/v1/config/volume</pre>
        </div>
        
        <div class="example">
            <strong>Set secure value:</strong>
            <pre class="code">curl -X POST -H "Content-Type: application/json" \\
     -d '{{"value":"secret","secure":true}}' \\
     http://{self.host}:{self.port}/api/v1/config/password</pre>
        </div>
        
        <div class="example">
            <strong>Delete configuration:</strong>
            <pre class="code">curl -X DELETE http://{self.host}:{self.port}/api/v1/config/volume</pre>
        </div>
        
        <h2 id="errors">Error Responses</h2>
        
        <table>
            <thead>
                <tr>
                    <th>HTTP Code</th>
                    <th>Description</th>
                    <th>Example Response</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>400</td>
                    <td>Bad Request</td>
                    <td><code>{{"status": "error", "message": "Missing required field: value"}}</code></td>
                </tr>
                <tr>
                    <td>404</td>
                    <td>Not Found</td>
                    <td><code>{{"status": "error", "message": "Configuration key not found"}}</code></td>
                </tr>
                <tr>
                    <td>500</td>
                    <td>Internal Server Error</td>
                    <td><code>{{"status": "error", "message": "Failed to retrieve configuration data"}}</code></td>
                </tr>
            </tbody>
        </table>
        
        <h2>Additional Resources</h2>
        <ul>
            <li><a href="/api/v1/openapi.json">OpenAPI 3.0 Specification</a> - Machine-readable API specification</li>
            <li><a href="/health">Health Check</a> - Server status endpoint</li>
        </ul>
        
        <hr style="margin: 30px 0;">
        <p style="text-align: center; color: #7f8c8d; font-size: 14px;">
            HiFiBerry Configuration API v1.7.0 | 
            <a href="mailto:info@hifiberry.com" style="color: #3498db;">Contact Support</a>
        </p>
    </div>
</body>
</html>
"""
        return html
    
    def _register_routes(self):
        """Register all API routes"""
        
        # API Documentation endpoint
        @self.app.route('/', methods=['GET'])
        @self.app.route('/docs', methods=['GET'])
        def api_documentation():
            """Serve API documentation"""
            # Check if request accepts HTML (browser request)
            if 'text/html' in request.headers.get('Accept', ''):
                return self._get_html_documentation()
            
            # Return JSON documentation for API clients
            docs = {
                'service': 'HiFiBerry Configuration API',
                'version': '1.7.0',
                'description': 'REST API for HiFiBerry configuration database access',
                'base_url': f'http://{self.host}:{self.port}',
                'endpoints': {
                    'health': {
                        'path': '/health',
                        'method': 'GET',
                        'description': 'Health check endpoint',
                        'response': {
                            'status': 'healthy',
                            'service': 'hifiberry-config-api',
                            'version': '1.7.0'
                        }
                    },
                    'get_all_config': {
                        'path': '/api/v1/config',
                        'method': 'GET',
                        'description': 'Get all configuration key-value pairs',
                        'parameters': {
                            'prefix': 'Optional. Filter keys by prefix'
                        },
                        'response': {
                            'status': 'success',
                            'data': {'key1': 'value1', 'key2': 'value2'},
                            'count': 2
                        }
                    },
                    'get_config_keys': {
                        'path': '/api/v1/config/keys',
                        'method': 'GET',
                        'description': 'Get all configuration keys',
                        'parameters': {
                            'prefix': 'Optional. Filter keys by prefix'
                        },
                        'response': {
                            'status': 'success',
                            'data': ['key1', 'key2'],
                            'count': 2
                        }
                    },
                    'get_config_value': {
                        'path': '/api/v1/config/<key>',
                        'method': 'GET',
                        'description': 'Get a specific configuration value',
                        'parameters': {
                            'key': 'Required. Configuration key name (in URL path)',
                            'secure': 'Optional. Set to "true" for secure/encrypted values',
                            'default': 'Optional. Default value if key not found'
                        },
                        'response': {
                            'status': 'success',
                            'data': {
                                'key': 'volume',
                                'value': '75'
                            }
                        },
                        'example': 'GET /api/v1/config/volume?default=50'
                    },
                    'set_config_value': {
                        'path': '/api/v1/config/<key>',
                        'method': 'PUT/POST',
                        'description': 'Set a configuration value',
                        'parameters': {
                            'key': 'Required. Configuration key name (in URL path)'
                        },
                        'body': {
                            'value': 'Required. The value to set (will be converted to string)',
                            'secure': 'Optional. Set to true for secure/encrypted storage'
                        },
                        'response': {
                            'status': 'success',
                            'message': 'Configuration key "volume" set successfully',
                            'data': {
                                'key': 'volume',
                                'value': '75'
                            }
                        },
                        'example': 'POST /api/v1/config/volume with body: {"value": "75"}'
                    },
                    'delete_config_value': {
                        'path': '/api/v1/config/<key>',
                        'method': 'DELETE',
                        'description': 'Delete a configuration value',
                        'parameters': {
                            'key': 'Required. Configuration key name (in URL path)'
                        },
                        'response': {
                            'status': 'success',
                            'message': 'Configuration key "volume" deleted successfully'
                        },
                        'example': 'DELETE /api/v1/config/volume'
                    }
                },
                'error_responses': {
                    '400': {
                        'description': 'Bad Request - Invalid input or missing required fields',
                        'example': {
                            'status': 'error',
                            'message': 'Missing required field: value'
                        }
                    },
                    '404': {
                        'description': 'Not Found - Configuration key does not exist',
                        'example': {
                            'status': 'error',
                            'message': 'Configuration key "nonexistent" not found'
                        }
                    },
                    '500': {
                        'description': 'Internal Server Error - Database or system error',
                        'example': {
                            'status': 'error',
                            'message': 'Failed to retrieve configuration data'
                        }
                    }
                },
                'examples': {
                    'curl_commands': [
                        {
                            'description': 'Get all configuration',
                            'command': f'curl http://{self.host}:{self.port}/api/v1/config'
                        },
                        {
                            'description': 'Get specific configuration value',
                            'command': f'curl http://{self.host}:{self.port}/api/v1/config/volume'
                        },
                        {
                            'description': 'Set configuration value',
                            'command': f'curl -X POST -H "Content-Type: application/json" -d \'{{"value":"75"}}\' http://{self.host}:{self.port}/api/v1/config/volume'
                        },
                        {
                            'description': 'Delete configuration value',
                            'command': f'curl -X DELETE http://{self.host}:{self.port}/api/v1/config/volume'
                        },
                        {
                            'description': 'Get keys with prefix filter',
                            'command': f'curl http://{self.host}:{self.port}/api/v1/config/keys?prefix=audio'
                        }
                    ]
                }
            }
            return jsonify(docs)
        
        # OpenAPI/Swagger specification endpoint
        @self.app.route('/api/v1/openapi.json', methods=['GET'])
        def openapi_spec():
            """OpenAPI 3.0 specification for the API"""
            spec = {
                'openapi': '3.0.0',
                'info': {
                    'title': 'HiFiBerry Configuration API',
                    'description': 'REST API for accessing and managing HiFiBerry configuration database',
                    'version': '1.7.0',
                    'contact': {
                        'name': 'HiFiBerry Team',
                        'email': 'info@hifiberry.com'
                    }
                },
                'servers': [
                    {
                        'url': f'http://{self.host}:{self.port}',
                        'description': 'HiFiBerry Configuration API Server'
                    }
                ],
                'paths': {
                    '/health': {
                        'get': {
                            'summary': 'Health Check',
                            'description': 'Check if the API server is running and healthy',
                            'responses': {
                                '200': {
                                    'description': 'Server is healthy',
                                    'content': {
                                        'application/json': {
                                            'schema': {
                                                'type': 'object',
                                                'properties': {
                                                    'status': {'type': 'string', 'example': 'healthy'},
                                                    'service': {'type': 'string', 'example': 'hifiberry-config-api'},
                                                    'version': {'type': 'string', 'example': '1.6.8'}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    '/api/v1/config': {
                        'get': {
                            'summary': 'Get All Configuration',
                            'description': 'Retrieve all configuration key-value pairs',
                            'parameters': [
                                {
                                    'name': 'prefix',
                                    'in': 'query',
                                    'description': 'Filter keys by prefix',
                                    'required': False,
                                    'schema': {'type': 'string'}
                                }
                            ],
                            'responses': {
                                '200': {
                                    'description': 'Configuration data retrieved successfully',
                                    'content': {
                                        'application/json': {
                                            'schema': {
                                                'type': 'object',
                                                'properties': {
                                                    'status': {'type': 'string', 'example': 'success'},
                                                    'data': {'type': 'object', 'example': {'volume': '75', 'soundcard': 'hifiberry-dac'}},
                                                    'count': {'type': 'integer', 'example': 2}
                                                }
                                            }
                                        }
                                    }
                                },
                                '500': {'$ref': '#/components/responses/InternalServerError'}
                            }
                        }
                    },
                    '/api/v1/config/keys': {
                        'get': {
                            'summary': 'Get Configuration Keys',
                            'description': 'Retrieve all configuration keys',
                            'parameters': [
                                {
                                    'name': 'prefix',
                                    'in': 'query',
                                    'description': 'Filter keys by prefix',
                                    'required': False,
                                    'schema': {'type': 'string'}
                                }
                            ],
                            'responses': {
                                '200': {
                                    'description': 'Configuration keys retrieved successfully',
                                    'content': {
                                        'application/json': {
                                            'schema': {
                                                'type': 'object',
                                                'properties': {
                                                    'status': {'type': 'string', 'example': 'success'},
                                                    'data': {'type': 'array', 'items': {'type': 'string'}, 'example': ['volume', 'soundcard']},
                                                    'count': {'type': 'integer', 'example': 2}
                                                }
                                            }
                                        }
                                    }
                                },
                                '500': {'$ref': '#/components/responses/InternalServerError'}
                            }
                        }
                    },
                    '/api/v1/config/{key}': {
                        'get': {
                            'summary': 'Get Configuration Value',
                            'description': 'Retrieve a specific configuration value by key',
                            'parameters': [
                                {
                                    'name': 'key',
                                    'in': 'path',
                                    'description': 'Configuration key name',
                                    'required': True,
                                    'schema': {'type': 'string'}
                                },
                                {
                                    'name': 'secure',
                                    'in': 'query',
                                    'description': 'Access secure/encrypted values',
                                    'required': False,
                                    'schema': {'type': 'boolean', 'default': False}
                                },
                                {
                                    'name': 'default',
                                    'in': 'query',
                                    'description': 'Default value if key not found',
                                    'required': False,
                                    'schema': {'type': 'string'}
                                }
                            ],
                            'responses': {
                                '200': {
                                    'description': 'Configuration value retrieved successfully',
                                    'content': {
                                        'application/json': {
                                            'schema': {
                                                'type': 'object',
                                                'properties': {
                                                    'status': {'type': 'string', 'example': 'success'},
                                                    'data': {
                                                        'type': 'object',
                                                        'properties': {
                                                            'key': {'type': 'string', 'example': 'volume'},
                                                            'value': {'type': 'string', 'example': '75'}
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                },
                                '404': {'$ref': '#/components/responses/NotFound'},
                                '500': {'$ref': '#/components/responses/InternalServerError'}
                            }
                        },
                        'post': {
                            'summary': 'Set Configuration Value',
                            'description': 'Set or update a configuration value',
                            'parameters': [
                                {
                                    'name': 'key',
                                    'in': 'path',
                                    'description': 'Configuration key name',
                                    'required': True,
                                    'schema': {'type': 'string'}
                                }
                            ],
                            'requestBody': {
                                'required': True,
                                'content': {
                                    'application/json': {
                                        'schema': {
                                            'type': 'object',
                                            'required': ['value'],
                                            'properties': {
                                                'value': {'type': 'string', 'description': 'The value to set'},
                                                'secure': {'type': 'boolean', 'description': 'Store as secure/encrypted value', 'default': False}
                                            }
                                        },
                                        'example': {'value': '75', 'secure': False}
                                    }
                                }
                            },
                            'responses': {
                                '200': {
                                    'description': 'Configuration value set successfully',
                                    'content': {
                                        'application/json': {
                                            'schema': {
                                                'type': 'object',
                                                'properties': {
                                                    'status': {'type': 'string', 'example': 'success'},
                                                    'message': {'type': 'string', 'example': 'Configuration key "volume" set successfully'},
                                                    'data': {
                                                        'type': 'object',
                                                        'properties': {
                                                            'key': {'type': 'string', 'example': 'volume'},
                                                            'value': {'type': 'string', 'example': '75'}
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                },
                                '400': {'$ref': '#/components/responses/BadRequest'},
                                '500': {'$ref': '#/components/responses/InternalServerError'}
                            }
                        },
                        'put': {
                            'summary': 'Set Configuration Value',
                            'description': 'Set or update a configuration value (same as POST)',
                            'parameters': [
                                {
                                    'name': 'key',
                                    'in': 'path',
                                    'description': 'Configuration key name',
                                    'required': True,
                                    'schema': {'type': 'string'}
                                }
                            ],
                            'requestBody': {
                                'required': True,
                                'content': {
                                    'application/json': {
                                        'schema': {
                                            'type': 'object',
                                            'required': ['value'],
                                            'properties': {
                                                'value': {'type': 'string', 'description': 'The value to set'},
                                                'secure': {'type': 'boolean', 'description': 'Store as secure/encrypted value', 'default': False}
                                            }
                                        }
                                    }
                                }
                            },
                            'responses': {
                                '200': {
                                    'description': 'Configuration value set successfully'
                                },
                                '400': {'$ref': '#/components/responses/BadRequest'},
                                '500': {'$ref': '#/components/responses/InternalServerError'}
                            }
                        },
                        'delete': {
                            'summary': 'Delete Configuration Value',
                            'description': 'Delete a configuration key and its value',
                            'parameters': [
                                {
                                    'name': 'key',
                                    'in': 'path',
                                    'description': 'Configuration key name',
                                    'required': True,
                                    'schema': {'type': 'string'}
                                }
                            ],
                            'responses': {
                                '200': {
                                    'description': 'Configuration value deleted successfully',
                                    'content': {
                                        'application/json': {
                                            'schema': {
                                                'type': 'object',
                                                'properties': {
                                                    'status': {'type': 'string', 'example': 'success'},
                                                    'message': {'type': 'string', 'example': 'Configuration key "volume" deleted successfully'}
                                                }
                                            }
                                        }
                                    }
                                },
                                '500': {'$ref': '#/components/responses/InternalServerError'}
                            }
                        }
                    }
                },
                'components': {
                    'responses': {
                        'BadRequest': {
                            'description': 'Bad Request',
                            'content': {
                                'application/json': {
                                    'schema': {
                                        'type': 'object',
                                        'properties': {
                                            'status': {'type': 'string', 'example': 'error'},
                                            'message': {'type': 'string', 'example': 'Missing required field: value'}
                                        }
                                    }
                                }
                            }
                        },
                        'NotFound': {
                            'description': 'Not Found',
                            'content': {
                                'application/json': {
                                    'schema': {
                                        'type': 'object',
                                        'properties': {
                                            'status': {'type': 'string', 'example': 'error'},
                                            'message': {'type': 'string', 'example': 'Configuration key not found'}
                                        }
                                    }
                                }
                            }
                        },
                        'InternalServerError': {
                            'description': 'Internal Server Error',
                            'content': {
                                'application/json': {
                                    'schema': {
                                        'type': 'object',
                                        'properties': {
                                            'status': {'type': 'string', 'example': 'error'},
                                            'message': {'type': 'string', 'example': 'Internal server error'}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            return jsonify(spec)
        
        # Health check endpoint
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'service': 'hifiberry-config-api',
                'version': '1.7.0'
            })
        
        # ConfigDB endpoints
        @self.app.route('/api/v1/config', methods=['GET'])
        def get_all_config():
            """Get all configuration keys and values"""
            try:
                prefix = request.args.get('prefix')
                config_data = self.configdb.get_all(prefix)
                return jsonify({
                    'status': 'success',
                    'data': config_data,
                    'count': len(config_data)
                })
            except Exception as e:
                logger.error(f"Error getting all config: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to retrieve configuration data'
                }), 500
        
        @self.app.route('/api/v1/config/keys', methods=['GET'])
        def get_config_keys():
            """Get all configuration keys"""
            try:
                prefix = request.args.get('prefix')
                keys = self.configdb.list_keys(prefix)
                return jsonify({
                    'status': 'success',
                    'data': keys,
                    'count': len(keys)
                })
            except Exception as e:
                logger.error(f"Error getting config keys: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to retrieve configuration keys'
                }), 500
        
        @self.app.route('/api/v1/config/<key>', methods=['GET'])
        def get_config_value(key):
            """Get a specific configuration value"""
            try:
                secure = request.args.get('secure', 'false').lower() == 'true'
                default = request.args.get('default')
                
                value = self.configdb.get(key, default, secure)
                
                if value is None and default is None:
                    return jsonify({
                        'status': 'error',
                        'message': f'Configuration key "{key}" not found'
                    }), 404
                
                return jsonify({
                    'status': 'success',
                    'data': {
                        'key': key,
                        'value': value
                    }
                })
            except Exception as e:
                logger.error(f"Error getting config value for key {key}: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to retrieve configuration value'
                }), 500
        
        @self.app.route('/api/v1/config/<key>', methods=['PUT', 'POST'])
        def set_config_value(key):
            """Set a configuration value"""
            try:
                if not request.is_json:
                    return jsonify({
                        'status': 'error',
                        'message': 'Content-Type must be application/json'
                    }), 400
                
                data = request.get_json()
                if 'value' not in data:
                    return jsonify({
                        'status': 'error',
                        'message': 'Missing required field: value'
                    }), 400
                
                value = data['value']
                secure = data.get('secure', False)
                
                # Convert value to string if it's not already
                if not isinstance(value, str):
                    value = str(value)
                
                success = self.configdb.set(key, value, secure)
                
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': f'Configuration key "{key}" set successfully',
                        'data': {
                            'key': key,
                            'value': value
                        }
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to set configuration value'
                    }), 500
                    
            except Exception as e:
                logger.error(f"Error setting config value for key {key}: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to set configuration value'
                }), 500
        
        @self.app.route('/api/v1/config/<key>', methods=['DELETE'])
        def delete_config_value(key):
            """Delete a configuration value"""
            try:
                success = self.configdb.delete(key)
                
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': f'Configuration key "{key}" deleted successfully'
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to delete configuration value'
                    }), 500
                    
            except Exception as e:
                logger.error(f"Error deleting config value for key {key}: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to delete configuration value'
                }), 500
        
        # Error handlers
        @self.app.errorhandler(400)
        def bad_request(error):
            return jsonify({
                'status': 'error',
                'message': 'Bad request'
            }), 400
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                'status': 'error',
                'message': 'Resource not found'
            }), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({
                'status': 'error',
                'message': 'Internal server error'
            }), 500
    
    def run(self):
        """Start the API server"""
        logger.info(f"Starting HiFiBerry Configuration Server on {self.host}:{self.port}")
        try:
            self.app.run(
                host=self.host,
                port=self.port,
                debug=self.debug,
                threaded=True
            )
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            sys.exit(1)

def setup_logging(verbose=False):
    """Configure logging"""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    root_logger.addHandler(console_handler)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='HiFiBerry Configuration Server')
    
    parser.add_argument('--host', default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=1081,
                        help='Port to listen on (default: 1081)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_arguments()
    
    # Configure logging
    setup_logging(args.verbose)
    
    # Create and start the server
    server = ConfigAPIServer(
        host=args.host,
        port=args.port,
        debug=args.debug
    )
    
    server.run()

if __name__ == "__main__":
    main()
