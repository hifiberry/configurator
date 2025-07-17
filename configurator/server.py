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
    
    def _get_markdown_documentation(self):
        """Serve raw Markdown documentation"""
        try:
            # Try to find the Markdown documentation file in multiple locations
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            # First, try the local docs directory (for development)
            local_md_file = os.path.join(script_dir, '..', 'docs', 'api-documentation.md')
            
            # Then try the system installation location
            system_md_file = '/usr/share/doc/hifiberry-configurator/api-documentation.md'
            
            md_file = None
            for path in [local_md_file, system_md_file]:
                if os.path.exists(path):
                    md_file = path
                    break
            
            if md_file is None:
                raise FileNotFoundError("Markdown documentation file not found")
            
            # Read the Markdown file
            with open(md_file, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # Replace localhost:1081 with actual host:port
            md_content = md_content.replace('localhost:1081', f'{self.host}:{self.port}')
            
            return md_content
        except Exception as e:
            logger.error(f"Error loading Markdown documentation: {e}")
            return f"""# HiFiBerry Configuration API v1.7.0

## Error Loading Documentation

The API documentation could not be loaded. Please check the server logs for more information.

## Alternative Resources

- [OpenAPI 3.0 Specification](/api/v1/openapi.json) - Machine-readable API specification
"""
    
    def _register_routes(self):
        """Register all API routes"""
        
        # API Documentation endpoint
        @self.app.route('/', methods=['GET'])
        @self.app.route('/docs', methods=['GET'])
        def api_documentation():
            """Serve API documentation"""
            accept_header = request.headers.get('Accept', '')
            
            # Check if request accepts markdown
            if 'text/markdown' in accept_header or 'text/plain' in accept_header:
                return self._get_markdown_documentation(), 200, {'Content-Type': 'text/markdown; charset=utf-8'}
            # For HTML requests (browsers), redirect to markdown docs
            elif 'text/html' in accept_header:
                return self._get_markdown_documentation(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
            
            # Return JSON documentation for API clients
            docs = {
                'service': 'HiFiBerry Configuration API',
                'version': '1.7.0',
                'description': 'REST API for HiFiBerry configuration database access',
                'base_url': f'http://{self.host}:{self.port}',
                'endpoints': {
                    'version': {
                        'path': '/version',
                        'method': 'GET',
                        'description': 'Get version information and available endpoints',
                        'response': {
                            'service': 'hifiberry-config-api',
                            'version': '1.7.0',
                            'api_version': 'v1',
                            'description': 'HiFiBerry Configuration Server',
                            'endpoints': {
                                'version': '/version',
                                'config': '/api/v1/config',
                                'docs': '/docs',
                                'openapi': '/api/v1/openapi.json'
                            }
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
                        'path': '/api/v1/config/key/<key>',
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
                        'example': 'GET /api/v1/config/key/volume?default=50'
                    },
                    'set_config_value': {
                        'path': '/api/v1/config/key/<key>',
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
                        'example': 'POST /api/v1/config/key/volume with body: {"value": "75"}'
                    },
                    'delete_config_value': {
                        'path': '/api/v1/config/key/<key>',
                        'method': 'DELETE',
                        'description': 'Delete a configuration value',
                        'parameters': {
                            'key': 'Required. Configuration key name (in URL path)'
                        },
                        'response': {
                            'status': 'success',
                            'message': 'Configuration key "volume" deleted successfully'
                        },
                        'example': 'DELETE /api/v1/config/key/volume'
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
                            'description': 'Get version information',
                            'command': f'curl http://{self.host}:{self.port}/version'
                        },
                        {
                            'description': 'Get all configuration',
                            'command': f'curl http://{self.host}:{self.port}/api/v1/config'
                        },
                        {
                            'description': 'Get specific configuration value',
                            'command': f'curl http://{self.host}:{self.port}/api/v1/config/key/volume'
                        },
                        {
                            'description': 'Set configuration value',
                            'command': f'curl -X POST -H "Content-Type: application/json" -d \'{{"value":"75"}}\' http://{self.host}:{self.port}/api/v1/config/key/volume'
                        },
                        {
                            'description': 'Delete configuration value',
                            'command': f'curl -X DELETE http://{self.host}:{self.port}/api/v1/config/key/volume'
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
                    '/version': {
                        'get': {
                            'summary': 'Version Information',
                            'description': 'Get version information and available endpoints',
                            'responses': {
                                '200': {
                                    'description': 'Version information',
                                    'content': {
                                        'application/json': {
                                            'schema': {
                                                'type': 'object',
                                                'properties': {
                                                    'service': {'type': 'string', 'example': 'hifiberry-config-api'},
                                                    'version': {'type': 'string', 'example': '1.7.0'},
                                                    'api_version': {'type': 'string', 'example': 'v1'},
                                                    'description': {'type': 'string', 'example': 'HiFiBerry Configuration Server'},
                                                    'endpoints': {
                                                        'type': 'object',
                                                        'example': {
                                                            'version': '/version',
                                                            'config': '/api/v1/config',
                                                            'docs': '/docs',
                                                            'openapi': '/api/v1/openapi.json'
                                                        }
                                                    }
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
                    '/api/v1/config/key/{key}': {
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
        
        # Version endpoint
        @self.app.route('/version', methods=['GET'])
        @self.app.route('/api/v1/version', methods=['GET'])
        def get_version():
            """Get version information"""
            return jsonify({
                'service': 'hifiberry-config-api',
                'version': '1.7.0',
                'api_version': 'v1',
                'description': 'HiFiBerry Configuration Server',
                'endpoints': {
                    'version': '/version',
                    'config': '/api/v1/config',
                    'docs': '/docs',
                    'openapi': '/api/v1/openapi.json'
                }
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
        
        @self.app.route('/api/v1/config/key/<key>', methods=['GET'])
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
        
        @self.app.route('/api/v1/config/key/<key>', methods=['PUT', 'POST'])
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
        
        @self.app.route('/api/v1/config/key/<key>', methods=['DELETE'])
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
