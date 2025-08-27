#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Marvel Collector Bot - Web App Module
Provides a mini web interface for bot users
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from aiohttp import web, ClientSession
from aiohttp.web import Request, Response
try:
    from aiohttp_cors import setup as cors_setup
    CORS_AVAILABLE = True
except ImportError:
    CORS_AVAILABLE = False
    cors_setup = None
import asyncpg

from modules.postgres_database import get_database
from modules.ban_manager import check_user_ban_status

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebApp:
    def __init__(self, bot_client):
        self.bot_client = bot_client
        self.app = web.Application()
        self.setup_routes()
        self.setup_cors()
        
    def setup_cors(self):
        """Setup CORS for cross-origin requests"""
        if CORS_AVAILABLE and cors_setup:
            try:
                cors = cors_setup(self.app, defaults={
                    "*": cors_setup.ResourceOptions(
                        allow_credentials=True,
                        expose_headers="*",
                        allow_headers="*",
                        allow_methods="*"
                    )
                })
                
                # Add CORS to all routes
                for route in list(self.app.router.routes()):
                    cors.add(route)
                logger.info("CORS setup completed successfully")
            except Exception as e:
                logger.warning(f"CORS setup failed, continuing without CORS: {e}")
        else:
            logger.info("CORS not available, continuing without CORS")
    
    def setup_routes(self):
        """Setup all web app routes"""
        # Main routes
        self.app.router.add_get('/', self.index_handler)
        self.app.router.add_get('/api/user/{user_id}', self.get_user_data)
        self.app.router.add_get('/api/collection/{user_id}', self.get_user_collection)
        self.app.router.add_get('/api/stats/{user_id}', self.get_user_stats)
        self.app.router.add_get('/api/characters', self.get_characters)
        self.app.router.add_get('/api/leaderboard', self.get_leaderboard)
        
        # WebSocket for real-time updates
        self.app.router.add_get('/ws', self.websocket_handler)
    
    async def index_handler(self, request: Request) -> Response:
        """Serve the main web app page"""
        html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Marvel Collector Bot - Web App</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .gradient-bg {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .card-hover {
            transition: all 0.3s ease;
        }
        .card-hover:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        }
        .character-card {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        .stats-card {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        .leaderboard-card {
            background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
        }
        
        /* Dark mode support */
        .dark body {
            background-color: #1f2937;
            color: #f9fafb;
        }
        
        .dark .bg-white {
            background-color: #374151;
            color: #f9fafb;
        }
        
        .dark .text-gray-800 {
            color: #f9fafb;
        }
        
        .dark .text-gray-600 {
            color: #d1d5db;
        }
        
        .dark .bg-gray-50 {
            background-color: #4b5563;
        }
        
        /* Mobile optimization for Telegram Web App */
        :root {
            --vh: 1vh;
        }
        
        @media (max-width: 768px) {
            .max-w-7xl {
                max-width: 100%;
                padding-left: 1rem;
                padding-right: 1rem;
            }
            
            .grid-cols-2 {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .grid-cols-4 {
                grid-template-columns: repeat(3, 1fr);
            }
            
            .grid-cols-6 {
                grid-template-columns: repeat(4, 1fr);
            }
        }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
                <!-- Navigation -->
            <nav class="gradient-bg text-white shadow-lg">
                <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div class="flex justify-between items-center py-4">
                        <div class="flex items-center space-x-3">
                            <i class="fas fa-robot text-2xl"></i>
                            <h1 class="text-xl font-bold">Marvel Collector Bot</h1>
                        </div>
                        <div class="flex items-center space-x-4">
                            <button id="connectBtn" class="bg-white text-purple-600 px-4 py-2 rounded-lg font-semibold hover:bg-gray-100 transition-colors">
                                <i class="fas fa-link mr-2"></i>Connect Bot
                            </button>
                            <button id="logoutBtn" class="hidden bg-red-500 text-white px-4 py-2 rounded-lg font-semibold hover:bg-red-600 transition-colors">
                                <i class="fas fa-sign-out-alt mr-2"></i>Logout
                            </button>
                        </div>
                    </div>
                </div>
            </nav>

    <!-- Main Content -->
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <!-- Welcome Section -->
        <div class="text-center mb-12">
            <h2 class="text-4xl font-bold text-gray-800 mb-4">Welcome to Marvel Collector Bot</h2>
            <p class="text-xl text-gray-600 max-w-3xl mx-auto">
                Access your collection, view stats, and manage your characters through this web interface.
                Connect your bot account to get started!
            </p>
        </div>

        <!-- Connection Form -->
        <div id="connectionForm" class="max-w-md mx-auto mb-12 bg-white rounded-lg shadow-lg p-6">
            <h3 class="text-xl font-semibold text-gray-800 mb-4 text-center">Connect Your Account</h3>
            <div class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Your User ID</label>
                    <input type="text" id="userId" placeholder="Enter your Telegram user ID" 
                           class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500">
                </div>
                <button onclick="connectAccount()" 
                        class="w-full gradient-bg text-white py-2 px-4 rounded-md hover:opacity-90 transition-opacity font-semibold">
                    <i class="fas fa-sign-in-alt mr-2"></i>Connect
                </button>
            </div>
            <div class="mt-4 text-center">
                <p class="text-sm text-gray-600">Your User ID is automatically filled from the bot link</p>
            </div>
        </div>

        <!-- Dashboard (Hidden until connected) -->
        <div id="dashboard" class="hidden">
            <!-- Stats Cards -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div class="stats-card text-white rounded-lg p-6 card-hover">
                    <div class="flex items-center">
                        <div class="p-3 bg-white bg-opacity-20 rounded-full">
                            <i class="fas fa-users text-2xl"></i>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm opacity-90">Total Characters</p>
                            <p class="text-2xl font-bold" id="totalCharacters">0</p>
                        </div>
                    </div>
                </div>
                
                <div class="stats-card text-white rounded-lg p-6 card-hover">
                    <div class="flex items-center">
                        <div class="p-3 bg-white bg-opacity-20 rounded-full">
                            <i class="fas fa-star text-2xl"></i>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm opacity-90">Rare Characters</p>
                            <p class="text-2xl font-bold" id="rareCharacters">0</p>
                        </div>
                    </div>
                </div>
                
                <div class="stats-card text-white rounded-lg p-6 card-hover">
                    <div class="flex items-center">
                        <div class="p-3 bg-white bg-opacity-20 rounded-full">
                            <i class="fas fa-trophy text-2xl"></i>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm opacity-90">Rank</p>
                            <p class="text-2xl font-bold" id="userRank">#0</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Collection Preview -->
            <div class="bg-white rounded-lg shadow-lg p-6 mb-8">
                <h3 class="text-xl font-semibold text-gray-800 mb-4">
                    <i class="fas fa-book-open mr-2"></i>Your Collection Preview
                </h3>
                <div id="collectionPreview" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    <!-- Collection items will be loaded here -->
                </div>
                <div class="text-center mt-4">
                    <button onclick="loadMoreCollection()" class="text-purple-600 hover:text-purple-800 font-semibold">
                        <i class="fas fa-arrow-down mr-2"></i>Load More
                    </button>
                </div>
            </div>

            <!-- Leaderboard -->
            <div class="bg-white rounded-lg shadow-lg p-6">
                <h3 class="text-xl font-semibold text-gray-800 mb-4">
                    <i class="fas fa-medal mr-2"></i>Top Collectors
                </h3>
                <div id="leaderboard" class="space-y-3">
                    <!-- Leaderboard will be loaded here -->
                </div>
            </div>
        </div>

        <!-- Loading Spinner -->
        <div id="loadingSpinner" class="hidden text-center py-8">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
            <p class="mt-2 text-gray-600">Loading...</p>
        </div>

        <!-- Error Message -->
        <div id="errorMessage" class="hidden bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            <span id="errorText"></span>
        </div>
    </div>

    <!-- Footer -->
    <footer class="bg-gray-800 text-white py-8 mt-16">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <p>&copy; 2024 Marvel Collector Bot. All rights reserved.</p>
            <p class="text-gray-400 mt-2">Powered by Pyrogram & aiohttp</p>
        </div>
    </footer>

    <script>
        let currentUserId = null;
        let ws = null;
        let tg = null;
        
        // Initialize Telegram Web App
        function initTelegramWebApp() {
            if (window.Telegram && window.Telegram.WebApp) {
                tg = window.Telegram.WebApp;
                
                // Initialize the Web App
                tg.ready();
                
                // Set the main button if needed
                if (tg.MainButton) {
                    tg.MainButton.setText('CONNECT ACCOUNT');
                    tg.MainButton.onClick(connectAccount);
                }
                
                // Handle back button
                if (tg.BackButton) {
                    tg.BackButton.onClick(function() {
                        if (document.getElementById('dashboard').classList.contains('hidden')) {
                            // If on connection form, close the web app
                            tg.close();
                        } else {
                            // If on dashboard, go back to connection form
                            goBackToConnection();
                        }
                    });
                }
                
                // Set theme
                tg.setHeaderColor('#667eea');
                tg.setBackgroundColor('#f3f4f6');
                
                // Handle theme changes
                tg.onEvent('themeChanged', function() {
                    const isDark = tg.colorScheme === 'dark';
                    document.body.classList.toggle('dark', isDark);
                    console.log('Theme changed to:', tg.colorScheme);
                });
                
                // Handle viewport changes
                tg.onEvent('viewportChanged', function() {
                    if (tg.viewportHeight) {
                        document.documentElement.style.setProperty('--vh', `${tg.viewportHeight * 0.01}px`);
                    }
                });
                
                // Handle main button visibility
                tg.onEvent('mainButtonClicked', function() {
                    console.log('Main button clicked');
                });
                
                // Handle web app closing
                tg.onEvent('closing', function() {
                    console.log('Telegram Web App is closing');
                    // Clean up any resources if needed
                });
                
                // Expand the Web App to full height
                tg.expand();
                
                // Set viewport for better mobile experience
                if (tg.viewportHeight) {
                    document.documentElement.style.setProperty('--vh', `${tg.viewportHeight * 0.01}px`);
                }
                
                console.log('Telegram Web App initialized');
                
                // Auto-fill user ID from Telegram user data if available
                if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                    const telegramUserId = tg.initDataUnsafe.user.id;
                    if (telegramUserId) {
                        document.getElementById('userId').value = telegramUserId;
                        currentUserId = telegramUserId.toString();
                        // Auto-connect if we have the user ID
                        setTimeout(() => {
                            connectAccount();
                        }, 500);
                    }
                }
            } else {
                console.log('Telegram Web App not available, running in regular browser');
            }
        }

        // Connect to WebSocket
        function connectWebSocket() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onopen = function() {
                console.log('WebSocket connected');
                if (currentUserId) {
                    ws.send(JSON.stringify({type: 'auth', userId: currentUserId}));
                }
            };
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            };
            
            ws.onclose = function() {
                console.log('WebSocket disconnected');
                setTimeout(connectWebSocket, 5000); // Reconnect after 5 seconds
            };
        }

        // Handle WebSocket messages
        function handleWebSocketMessage(data) {
            switch(data.type) {
                case 'stats_update':
                    updateStats(data.stats);
                    break;
                case 'collection_update':
                    updateCollection(data.collection);
                    break;
                case 'leaderboard_update':
                    updateLeaderboard(data.leaderboard);
                    break;
            }
        }

        // Connect account
        async function connectAccount() {
            const userId = document.getElementById('userId').value.trim();
            if (!userId) {
                showError('Please enter your user ID');
                return;
            }

            showLoading(true);
            try {
                const response = await fetch(`/api/user/${userId}`);
                if (response.ok) {
                    const userData = await response.json();
                    currentUserId = userId;
                    document.getElementById('connectionForm').classList.add('hidden');
                    document.getElementById('dashboard').classList.remove('hidden');
                    
                    // Show logout button
                    document.getElementById('logoutBtn').classList.remove('hidden');
                    
                    // Update Telegram Web App UI
                    if (tg && tg.MainButton) {
                        tg.MainButton.hide();
                    }
                    
                    // Show back button in Telegram Web App
                    if (tg && tg.BackButton) {
                        tg.BackButton.show();
                    }
                    
                    // Show success message
                    showSuccess('Successfully connected to your account!');
                    
                    loadUserData(userId);
                    connectWebSocket();
                } else {
                    showError('User not found. Please check your user ID.');
                }
            } catch (error) {
                showError('Connection failed. Please try again.');
            } finally {
                showLoading(false);
            }
        }

        // Load user data
        async function loadUserData(userId) {
            try {
                // Load stats
                const statsResponse = await fetch(`/api/stats/${userId}`);
                if (statsResponse.ok) {
                    const stats = await statsResponse.json();
                    updateStats(stats);
                }

                // Load collection preview
                const collectionResponse = await fetch(`/api/collection/${userId}?limit=12`);
                if (collectionResponse.ok) {
                    const collection = await collectionResponse.json();
                    updateCollection(collection);
                }

                // Load leaderboard
                const leaderboardResponse = await fetch('/api/leaderboard');
                if (leaderboardResponse.ok) {
                    const leaderboard = await leaderboardResponse.json();
                    updateLeaderboard(leaderboard);
                }
            } catch (error) {
                console.error('Error loading user data:', error);
            }
        }

        // Update stats display
        function updateStats(stats) {
            document.getElementById('totalCharacters').textContent = stats.total_characters || 0;
            document.getElementById('rareCharacters').textContent = stats.rare_characters || 0;
            document.getElementById('userRank').textContent = `#${stats.rank || 0}`;
        }

        // Update collection display
        function updateCollection(collection) {
            const container = document.getElementById('collectionPreview');
            container.innerHTML = '';

            collection.characters.forEach(character => {
                const characterCard = document.createElement('div');
                characterCard.className = 'character-card text-white rounded-lg p-4 text-center card-hover';
                characterCard.innerHTML = `
                    <div class="text-2xl mb-2">${character.emoji || '👤'}</div>
                    <div class="text-sm font-semibold truncate">${character.name}</div>
                    <div class="text-xs opacity-90">${character.anime}</div>
                    <div class="text-xs opacity-75">${character.rarity}</div>
                `;
                container.appendChild(characterCard);
            });
        }

        // Update leaderboard display
        function updateLeaderboard(leaderboard) {
            const container = document.getElementById('leaderboard');
            container.innerHTML = '';

            leaderboard.top_users.forEach((user, index) => {
                const rank = index + 1;
                const medal = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `#${rank}`;
                
                const userRow = document.createElement('div');
                userRow.className = 'flex items-center justify-between p-3 bg-gray-50 rounded-lg';
                userRow.innerHTML = `
                    <div class="flex items-center space-x-3">
                        <span class="text-lg">${medal}</span>
                        <span class="font-semibold">${user.username || 'Unknown'}</span>
                    </div>
                    <span class="text-purple-600 font-bold">${user.total_characters}</span>
                `;
                container.appendChild(userRow);
            });
        }

        // Load more collection items
        function loadMoreCollection() {
            if (currentUserId) {
                loadUserData(currentUserId);
            }
        }

        // Show/hide loading spinner
        function showLoading(show) {
            document.getElementById('loadingSpinner').classList.toggle('hidden', !show);
        }

        // Show error message
        function showError(message) {
            document.getElementById('errorText').textContent = message;
            document.getElementById('errorMessage').classList.remove('hidden');
            
            // Haptic feedback for Telegram Web App
            if (tg && tg.HapticFeedback) {
                tg.HapticFeedback.impactOccurred('medium');
            }
            
            // Show error in Telegram Web App
            if (tg && tg.showAlert) {
                tg.showAlert(message);
            }
            
            setTimeout(() => {
                document.getElementById('errorMessage').classList.add('hidden');
            }, 5000);
        }
        
        // Show success message
        function showSuccess(message) {
            // Haptic feedback for Telegram Web App
            if (tg && tg.HapticFeedback) {
                tg.HapticFeedback.notificationOccurred('success');
            }
            
            // Show success in Telegram Web App
            if (tg && tg.showAlert) {
                tg.showAlert(message);
            }
        }
        
        // Handle user going back to connection form
        function goBackToConnection() {
            document.getElementById('dashboard').classList.add('hidden');
            document.getElementById('connectionForm').classList.remove('hidden');
            
            // Hide logout button
            document.getElementById('logoutBtn').classList.add('hidden');
            
            // Update Telegram Web App UI
            if (tg && tg.MainButton) {
                tg.MainButton.show();
                tg.MainButton.setText('CONNECT ACCOUNT');
            }
            if (tg && tg.BackButton) {
                tg.BackButton.hide();
            }
            
            // Clear current user ID
            currentUserId = null;
            
            // Show success message
            showSuccess('Returned to connection form');
        }

        // Initialize WebSocket connection and auto-fill user ID
        document.addEventListener('DOMContentLoaded', function() {
            // Initialize Telegram Web App first
            initTelegramWebApp();
            
            connectWebSocket();
            
            // Auto-fill user ID from URL query parameter (fallback for non-Telegram users)
            const urlParams = new URLSearchParams(window.location.search);
            const userId = urlParams.get('user_id');
            if (userId && !currentUserId) {
                document.getElementById('userId').value = userId;
                // Auto-connect if user ID is provided
                setTimeout(() => {
                    connectAccount();
                }, 500);
            }
            
            // Add keyboard event listener for Enter key
            document.getElementById('userId').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    connectAccount();
                }
            });
            
            // Add logout button event listener
            document.getElementById('logoutBtn').addEventListener('click', goBackToConnection);
        });
    </script>
</body>
</html>
        """
        return web.Response(text=html_content, content_type='text/html')
    
    async def get_user_data(self, request: Request) -> Response:
        """Get user data by user ID"""
        try:
            user_id = int(request.match_info['user_id'])
            db = get_database()
            
            # Check if user exists and is not banned
            is_banned, _ = await check_user_ban_status(user_id, db)
            if is_banned:
                return web.Response(status=403, text="User is banned")
            
            # Get user data
            user_query = "SELECT id, username, first_name, last_name, created_at FROM users WHERE id = $1"
            user = await db.fetchrow(user_query, user_id)
            
            if not user:
                return web.Response(status=404, text="User not found")
            
            user_data = {
                'id': user['id'],
                'username': user['username'],
                'first_name': user['first_name'],
                'last_name': user['last_name'],
                'created_at': user['created_at'].isoformat() if user['created_at'] else None
            }
            
            return web.json_response(user_data)
            
        except ValueError:
            return web.Response(status=400, text="Invalid user ID")
        except Exception as e:
            logger.error(f"Error getting user data: {e}")
            return web.Response(status=500, text="Internal server error")
    
    async def get_user_collection(self, request: Request) -> Response:
        """Get user's character collection"""
        try:
            user_id = int(request.match_info['user_id'])
            limit = int(request.query.get('limit', 50))
            offset = int(request.query.get('offset', 0))
            
            db = get_database()
            
            # Check if user exists and is not banned
            is_banned, _ = await check_user_ban_status(user_id, db)
            if is_banned:
                return web.Response(status=403, text="User is banned")
            
            # Get user's characters
            collection_query = """
                SELECT c.id, c.name, c.anime, c.rarity, c.image_url, c.created_at
                FROM characters c
                INNER JOIN user_characters uc ON c.id = uc.character_id
                WHERE uc.user_id = $1
                ORDER BY c.created_at DESC
                LIMIT $2 OFFSET $3
            """
            
            characters = await db.fetch(collection_query, user_id, limit, offset)
            
            # Get total count
            count_query = """
                SELECT COUNT(*) as total
                FROM user_characters
                WHERE user_id = $1
            """
            total = await db.fetchval(count_query, user_id)
            
            collection_data = {
                'user_id': user_id,
                'total': total,
                'characters': [
                    {
                        'id': char['id'],
                        'name': char['name'],
                        'anime': char['anime'],
                        'rarity': char['rarity'],
                        'image_url': char['image_url'],
                        'created_at': char['created_at'].isoformat() if char['created_at'] else None,
                        'emoji': self.get_rarity_emoji(char['rarity'])
                    }
                    for char in characters
                ]
            }
            
            return web.json_response(collection_data)
            
        except ValueError:
            return web.Response(status=400, text="Invalid parameters")
        except Exception as e:
            logger.error(f"Error getting user collection: {e}")
            return web.Response(status=500, text="Internal server error")
    
    async def get_user_stats(self, request: Request) -> Response:
        """Get user's collection statistics"""
        try:
            user_id = int(request.match_info['user_id'])
            db = get_database()
            
            # Check if user exists and is not banned
            is_banned, _ = await check_user_ban_status(user_id, db)
            if is_banned:
                return web.Response(status=403, text="User is banned")
            
            # Get user's stats
            stats_query = """
                SELECT 
                    COUNT(uc.character_id) as total_characters,
                    COUNT(CASE WHEN c.rarity IN ('SSR', 'UR', 'LR') THEN 1 END) as rare_characters,
                    COUNT(CASE WHEN c.rarity = 'SSR' THEN 1 END) as ssr_count,
                    COUNT(CASE WHEN c.rarity = 'UR' THEN 1 END) as ur_count,
                    COUNT(CASE WHEN c.rarity = 'LR' THEN 1 END) as lr_count
                FROM user_characters uc
                INNER JOIN characters c ON uc.character_id = c.id
                WHERE uc.user_id = $1
            """
            
            stats = await db.fetchrow(stats_query, user_id)
            
            # Get user's rank
            rank_query = """
                SELECT rank
                FROM (
                    SELECT 
                        uc.user_id,
                        COUNT(uc.character_id) as total_characters,
                        RANK() OVER (ORDER BY COUNT(uc.character_id) DESC) as rank
                    FROM user_characters uc
                    GROUP BY uc.user_id
                ) ranked
                WHERE user_id = $1
            """
            
            rank = await db.fetchval(rank_query, user_id)
            
            stats_data = {
                'total_characters': stats['total_characters'] or 0,
                'rare_characters': stats['rare_characters'] or 0,
                'ssr_count': stats['ssr_count'] or 0,
                'ur_count': stats['ur_count'] or 0,
                'lr_count': stats['lr_count'] or 0,
                'rank': rank or 0
            }
            
            return web.json_response(stats_data)
            
        except ValueError:
            return web.Response(status=400, text="Invalid user ID")
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return web.Response(status=500, text="Internal server error")
    
    async def get_characters(self, request: Request) -> Response:
        """Get all characters with pagination"""
        try:
            limit = int(request.query.get('limit', 50))
            offset = int(request.query.get('offset', 0))
            rarity = request.query.get('rarity')
            anime = request.query.get('anime')
            
            db = get_database()
            
            # Build query
            where_conditions = []
            query_params = [limit, offset]
            param_count = 2
            
            if rarity:
                where_conditions.append(f"rarity = ${param_count + 1}")
                query_params.append(rarity)
                param_count += 1
            
            if anime:
                where_conditions.append(f"anime ILIKE ${param_count + 1}")
                query_params.append(f"%{anime}%")
                param_count += 1
            
            where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            characters_query = f"""
                SELECT id, name, anime, rarity, image_url, created_at
                FROM characters
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${1} OFFSET ${2}
            """
            
            characters = await db.fetch(characters_query, *query_params)
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*) as total
                FROM characters
                {where_clause}
            """
            count_params = query_params[2:] if len(query_params) > 2 else []
            total = await db.fetchval(count_query, *count_params)
            
            characters_data = {
                'total': total,
                'characters': [
                    {
                        'id': char['id'],
                        'name': char['name'],
                        'anime': char['anime'],
                        'rarity': char['rarity'],
                        'image_url': char['image_url'],
                        'created_at': char['created_at'].isoformat() if char['created_at'] else None
                    }
                    for char in characters
                ]
            }
            
            return web.json_response(characters_data)
            
        except ValueError:
            return web.Response(status=400, text="Invalid parameters")
        except Exception as e:
            logger.error(f"Error getting characters: {e}")
            return web.Response(status=500, text="Internal server error")
    
    async def get_leaderboard(self, request: Request) -> Response:
        """Get top collectors leaderboard"""
        try:
            limit = int(request.query.get('limit', 10))
            db = get_database()
            
            leaderboard_query = """
                SELECT 
                    u.id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    COUNT(uc.character_id) as total_characters
                FROM users u
                INNER JOIN user_characters uc ON u.id = uc.user_id
                GROUP BY u.id, u.username, u.first_name, u.last_name
                ORDER BY total_characters DESC
                LIMIT $1
            """
            
            top_users = await db.fetch(leaderboard_query, limit)
            
            leaderboard_data = {
                'top_users': [
                    {
                        'id': user['id'],
                        'username': user['username'],
                        'first_name': user['first_name'],
                        'last_name': user['last_name'],
                        'total_characters': user['total_characters']
                    }
                    for user in top_users
                ]
            }
            
            return web.json_response(leaderboard_data)
            
        except ValueError:
            return web.Response(status=400, text="Invalid parameters")
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            return web.Response(status=500, text="Internal server error")
    
    async def websocket_handler(self, request: Request) -> web.WebSocketResponse:
        """Handle WebSocket connections for real-time updates"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        user_id = None
        
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get('type') == 'auth':
                            user_id = int(data.get('userId'))
                            await ws.send_str(json.dumps({
                                'type': 'auth_success',
                                'message': 'Authenticated successfully'
                            }))
                    except (json.JSONDecodeError, ValueError):
                        await ws.send_str(json.dumps({
                            'type': 'error',
                            'message': 'Invalid message format'
                        }))
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if user_id:
                logger.info(f"User {user_id} disconnected from WebSocket")
        
        return ws
    
    def get_rarity_emoji(self, rarity: str) -> str:
        """Get emoji for character rarity"""
        rarity_emojis = {
            'C': '⚪',
            'UC': '🟢',
            'R': '🔵',
            'SR': '🟣',
            'SSR': '🟡',
            'UR': '🟠',
            'LR': '🔴'
        }
        return rarity_emojis.get(rarity, '👤')
    
    async def start(self, host: str = '0.0.0.0', port: int = 8080):
        """Start the web app server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        logger.info(f"Web app started at http://{host}:{port}")
        return runner
    
    async def stop(self):
        """Stop the web app server"""
        if hasattr(self, 'runner'):
            await self.runner.cleanup()
