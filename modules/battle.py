from datetime import datetime
from typing import List, Dict, Optional, Tuple
import random
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from modules.postgres_database import get_database, get_postgres_pool
from modules.decorators import auto_register_user
from modules.team import TeamManager

# Battle system constants
MAX_TEAM_SIZE = 3
BATTLE_TIMEOUT = 300  # 5 minutes

# Type effectiveness chart (simplified)
TYPE_EFFECTIVENESS = {
    "Fire": {"Grass": 2.0, "Ice": 2.0, "Water": 0.5, "Rock": 0.5},
    "Water": {"Fire": 2.0, "Ground": 2.0, "Rock": 2.0, "Grass": 0.5, "Electric": 0.5},
    "Electric": {"Water": 2.0, "Flying": 2.0, "Ground": 0.0, "Grass": 0.5},
    "Grass": {"Water": 2.0, "Ground": 2.0, "Rock": 2.0, "Fire": 0.5, "Poison": 0.5, "Flying": 0.5, "Bug": 0.5},
    "Ice": {"Grass": 2.0, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Fire": 0.5, "Water": 0.5, "Steel": 0.5},
    "Fighting": {"Normal": 2.0, "Ice": 2.0, "Rock": 2.0, "Steel": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Ghost": 0.0},
    "Poison": {"Grass": 2.0, "Fairy": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0},
    "Ground": {"Fire": 2.0, "Electric": 2.0, "Poison": 2.0, "Rock": 2.0, "Steel": 2.0, "Grass": 0.5, "Bug": 0.5, "Flying": 0.0},
    "Flying": {"Grass": 2.0, "Fighting": 2.0, "Bug": 2.0, "Electric": 0.5, "Rock": 0.5, "Steel": 0.5},
    "Psychic": {"Fighting": 2.0, "Poison": 2.0, "Dark": 0.0, "Steel": 0.5},
    "Bug": {"Grass": 2.0, "Psychic": 2.0, "Dark": 2.0, "Fire": 0.5, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Ghost": 0.5, "Steel": 0.5, "Fairy": 0.5},
    "Rock": {"Fire": 2.0, "Ice": 2.0, "Flying": 2.0, "Bug": 2.0, "Fighting": 0.5, "Ground": 0.5, "Steel": 0.5},
    "Ghost": {"Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5, "Normal": 0.0},
    "Dragon": {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
    "Dark": {"Psychic": 2.0, "Ghost": 2.0, "Fighting": 0.5, "Dark": 0.5, "Fairy": 0.5},
    "Steel": {"Ice": 2.0, "Rock": 2.0, "Fairy": 2.0, "Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Steel": 0.5},
    "Fairy": {"Fighting": 2.0, "Dragon": 2.0, "Dark": 2.0, "Poison": 0.5, "Steel": 0.5, "Fire": 0.5}
}

# Rarity-based stats (ATK, SPE, HP, DEF) - Updated with proper progression
RARITY_STATS = {
    "Common": {"atk": 45, "spe": 40, "hp": 50, "def": 45},
    "Medium": {"atk": 60, "spe": 55, "hp": 65, "def": 60},
    "Rare": {"atk": 75, "spe": 70, "hp": 80, "def": 75},
    "Legendary": {"atk": 90, "spe": 85, "hp": 95, "def": 90},
    "Exclusive": {"atk": 105, "spe": 100, "hp": 110, "def": 105},
    "Elite": {"atk": 135, "spe": 130, "hp": 140, "def": 135},
    "Limited Edition": {"atk": 165, "spe": 160, "hp": 170, "def": 165},
    "Ultimate": {"atk": 150, "spe": 145, "hp": 155, "def": 150},
    "Premium": {"atk": 265, "spe": 260, "hp": 270, "def": 265},
    "Supreme": {"atk": 280, "spe": 275, "hp": 285, "def": 280},
    "Mythic": {"atk": 145, "spe": 140, "hp": 150, "def": 145},
    "Zenith": {"atk": 155, "spe": 150, "hp": 160, "def": 155},
    "Ethereal": {"atk": 170, "spe": 165, "hp": 175, "def": 170},
    "Mega Evolution": {"atk": 190, "spe": 185, "hp": 195, "def": 190}
}

# Rarity-based moves (4 moves per rarity) - Updated with real Pokemon moves and better accuracy
RARITY_MOVES = {
    "Common": [
        {"name": "Tackle", "power": 40, "accuracy": 100, "type": "Normal", "effect": "Basic physical attack"},
        {"name": "Growl", "power": 0, "accuracy": 100, "type": "Normal", "effect": "Lowers opponent's Attack"},
        {"name": "Scratch", "power": 40, "accuracy": 100, "type": "Normal", "effect": "Sharp claws attack"},
        {"name": "Leer", "power": 0, "accuracy": 100, "type": "Normal", "effect": "Lowers opponent's Defense"}
    ],
    "Medium": [
        {"name": "Quick Attack", "power": 40, "accuracy": 100, "type": "Normal", "effect": "Always goes first"},
        {"name": "Ember", "power": 40, "accuracy": 100, "type": "Fire", "effect": "May burn opponent"},
        {"name": "Water Gun", "power": 40, "accuracy": 100, "type": "Water", "effect": "Water blast attack"},
        {"name": "Thunder Shock", "power": 40, "accuracy": 100, "type": "Electric", "effect": "May paralyze opponent"}
    ],
    "Rare": [
        {"name": "Flamethrower", "power": 90, "accuracy": 100, "type": "Fire", "effect": "May burn opponent"},
        {"name": "Thunderbolt", "power": 90, "accuracy": 100, "type": "Electric", "effect": "May paralyze opponent"},
        {"name": "Ice Beam", "power": 90, "accuracy": 100, "type": "Ice", "effect": "May freeze opponent"},
        {"name": "Psychic", "power": 90, "accuracy": 100, "type": "Psychic", "effect": "May lower opponent's Special Defense"}
    ],
    "Legendary": [
        {"name": "Fire Blast", "power": 110, "accuracy": 85, "type": "Fire", "effect": "May burn opponent"},
        {"name": "Thunder", "power": 110, "accuracy": 70, "type": "Electric", "effect": "May paralyze opponent"},
        {"name": "Blizzard", "power": 110, "accuracy": 70, "type": "Ice", "effect": "May freeze opponent"},
        {"name": "Hyper Beam", "power": 150, "accuracy": 90, "type": "Normal", "effect": "Must recharge next turn"}
    ],
    "Exclusive": [
        {"name": "Dragon Claw", "power": 80, "accuracy": 100, "type": "Dragon", "effect": "Sharp dragon claws"},
        {"name": "Shadow Ball", "power": 80, "accuracy": 100, "type": "Ghost", "effect": "May lower opponent's Special Defense"},
        {"name": "Earthquake", "power": 100, "accuracy": 100, "type": "Ground", "effect": "Hits all adjacent Pokemon"},
        {"name": "Aerial Ace", "power": 60, "accuracy": 100, "type": "Flying", "effect": "Never misses"}
    ],
    "Elite": [
        {"name": "Dragon Rush", "power": 100, "accuracy": 75, "type": "Dragon", "effect": "May cause flinching"},
        {"name": "Focus Blast", "power": 120, "accuracy": 70, "type": "Fighting", "effect": "May lower opponent's Special Defense"},
        {"name": "Giga Impact", "power": 150, "accuracy": 90, "type": "Normal", "effect": "Must recharge next turn"},
        {"name": "Stone Edge", "power": 100, "accuracy": 80, "type": "Rock", "effect": "High critical hit ratio"}
    ],
    "Limited Edition": [
        {"name": "V-create", "power": 180, "accuracy": 95, "type": "Fire", "effect": "Lowers user's stats"},
        {"name": "Roar of Time", "power": 150, "accuracy": 90, "type": "Dragon", "effect": "Must recharge next turn"},
        {"name": "Spacial Rend", "power": 100, "accuracy": 95, "type": "Dragon", "effect": "High critical hit ratio"},
        {"name": "Judgment", "power": 100, "accuracy": 100, "type": "Normal", "effect": "Type varies with held item"}
    ],
    "Ultimate": [
        {"name": "Blue Flare", "power": 130, "accuracy": 85, "type": "Fire", "effect": "May burn opponent"},
        {"name": "Bolt Strike", "power": 130, "accuracy": 85, "type": "Electric", "effect": "May paralyze opponent"},
        {"name": "Glaciate", "power": 130, "accuracy": 85, "type": "Ice", "effect": "May freeze opponent"},
        {"name": "Dragon Ascent", "power": 120, "accuracy": 100, "type": "Flying", "effect": "Lowers user's defenses"}
    ],
    "Premium": [
        {"name": "Origin Pulse", "power": 110, "accuracy": 85, "type": "Water", "effect": "Legendary water attack"},
        {"name": "Precipice Blades", "power": 120, "accuracy": 85, "type": "Ground", "effect": "Legendary ground attack"},
        {"name": "Dragon Ascent", "power": 120, "accuracy": 100, "type": "Flying", "effect": "Legendary flying attack"},
        {"name": "Core Enforcer", "power": 100, "accuracy": 100, "type": "Dragon", "effect": "Nullifies abilities"}
    ],
    "Supreme": [
        {"name": "Light That Burns the Sky", "power": 200, "accuracy": 100, "type": "Psychic", "effect": "Ultimate psychic attack"},
        {"name": "Searing Sunraze Smash", "power": 200, "accuracy": 100, "type": "Steel", "effect": "Ultimate steel attack"},
        {"name": "Menacing Moonraze Maelstrom", "power": 200, "accuracy": 100, "type": "Ghost", "effect": "Ultimate ghost attack"},
        {"name": "Let's Snuggle Forever", "power": 190, "accuracy": 100, "type": "Fairy", "effect": "Ultimate fairy attack"}
    ],
    "Mythic": [
        {"name": "G-Max Wildfire", "power": 150, "accuracy": 90, "type": "Fire", "effect": "Mythic fire attack"},
        {"name": "G-Max Volt Crash", "power": 150, "accuracy": 90, "type": "Electric", "effect": "Mythic electric attack"},
        {"name": "G-Max Cannonade", "power": 150, "accuracy": 90, "type": "Water", "effect": "Mythic water attack"},
        {"name": "G-Max One Blow", "power": 150, "accuracy": 90, "type": "Fighting", "effect": "Mythic fighting attack"}
    ],
    "Zenith": [
        {"name": "Max Flare", "power": 130, "accuracy": 95, "type": "Fire", "effect": "Ultimate fire attack"},
        {"name": "Max Lightning", "power": 130, "accuracy": 95, "type": "Electric", "effect": "Ultimate electric attack"},
        {"name": "Max Geyser", "power": 130, "accuracy": 95, "type": "Water", "effect": "Ultimate water attack"},
        {"name": "Max Strike", "power": 130, "accuracy": 95, "type": "Normal", "effect": "Ultimate normal attack"}
    ],
    "Ethereal": [
        {"name": "Ethereal Blast", "power": 140, "accuracy": 90, "type": "Psychic", "effect": "Ethereal power attack"},
        {"name": "Ethereal Storm", "power": 140, "accuracy": 90, "type": "Flying", "effect": "Ethereal storm attack"},
        {"name": "Ethereal Surge", "power": 140, "accuracy": 90, "type": "Electric", "effect": "Ethereal surge attack"},
        {"name": "Ethereal Void", "power": 140, "accuracy": 90, "type": "Ghost", "effect": "Ethereal void attack"}
    ],
    "Mega Evolution": [
        {"name": "Mega Punch", "power": 80, "accuracy": 85, "type": "Normal", "effect": "Mega evolution power"},
        {"name": "Mega Kick", "power": 120, "accuracy": 75, "type": "Fighting", "effect": "Mega evolution power"},
        {"name": "Mega Drain", "power": 40, "accuracy": 100, "type": "Grass", "effect": "Mega evolution power"},
        {"name": "Mega Throw", "power": 100, "accuracy": 80, "type": "Rock", "effect": "Mega evolution power"}
    ]
}

class BattlePokemon:
    """Represents a Pokemon in battle with stats and moves"""
    
    def __init__(self, character_data: Dict):
        self.character_id = character_data['character_id']
        self.name = character_data['name']
        self.rarity = character_data['rarity']
        self.anime = character_data.get('anime', 'Unknown')
        self.level = 100  # All Pokemon are level 100 in battles
        
        # Get base stats from rarity
        base_stats = RARITY_STATS.get(self.rarity, RARITY_STATS["Common"])
        
        # Scale stats for level 100 (Pokemon formula: stat = ((base * 2 + IV + EV/4) * level / 100) + 5)
        # For simplicity, we'll use a level multiplier: level 100 = 2x base stats
        level_multiplier = 2.0
        
        self.max_hp = int(base_stats['hp'] * level_multiplier)
        self.current_hp = self.max_hp
        self.atk = int(base_stats['atk'] * level_multiplier)
        self.spe = int(base_stats['spe'] * level_multiplier)
        self.defense = int(base_stats['def'] * level_multiplier)
        
        # Get moves from rarity
        self.moves = RARITY_MOVES.get(self.rarity, RARITY_MOVES["Common"])
        
        # Battle status
        self.is_fainted = False
        self.status_effects = []
        self.stat_modifiers = {"atk": 0, "spe": 0, "def": 0, "spd": 0}
    
    def get_effective_stats(self) -> Dict:
        """Get current stats with modifiers applied"""
        modifiers = self.stat_modifiers
        return {
            "atk": max(1, self.atk + (self.atk * modifiers["atk"] // 100)),
            "spe": max(1, self.spe + (self.spe * modifiers["spe"] // 100)),
            "def": max(1, self.defense + (self.defense * modifiers["def"] // 100)),
            "spd": max(1, self.spe + (self.spe * modifiers["spd"] // 100))  # Speed based on special
        }
    
    def take_damage(self, damage: int) -> bool:
        """Take damage and return True if fainted"""
        self.current_hp = max(0, self.current_hp - damage)
        if self.current_hp <= 0:
            self.is_fainted = True
            return True
        return False
    
    def heal(self, amount: int):
        """Heal the Pokemon"""
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        if self.current_hp > 0:
            self.is_fainted = False
    
    def is_alive(self) -> bool:
        """Check if Pokemon is alive"""
        return not self.is_fainted and self.current_hp > 0
    
    def calculate_damage(self, move: Dict, target: 'BattlePokemon') -> tuple[int, bool]:
        """Calculate damage for a move using improved formula for level 100 Pokemon"""
        if move['power'] == 0:
            return 0, False  # Status move
        
        # Improved damage calculation for level 100 Pokemon
        # Formula: ((2 * Level / 5 + 2) * Power * Attack / Defense) / 50 + 2
        
        # Get effective stats
        attacker_stats = self.get_effective_stats()
        target_stats = target.get_effective_stats()
        
        # Calculate attack and defense
        if move['type'] in ['Fire', 'Water', 'Electric', 'Grass', 'Ice', 'Psychic', 'Dragon', 'Dark']:
            attack = attacker_stats['spe']
            defense = target_stats['spd']
        else:
            attack = attacker_stats['atk']
            defense = target_stats['def']
        
        # Apply STAB (Same Type Attack Bonus) - 1.5x if move type matches Pokemon type
        stab = 1.5 if move['type'] == self.rarity else 1.0
        
        # Apply type effectiveness
        type_effectiveness = 1.0
        if move['type'] in TYPE_EFFECTIVENESS and target.rarity in TYPE_EFFECTIVENESS[move['type']]:
            type_effectiveness = TYPE_EFFECTIVENESS[move['type']][target.rarity]
        
        # Random factor (0.85 to 1.0)
        random_factor = random.uniform(0.85, 1.0)
        
        # Critical hit chance (6.25%)
        is_critical = random.random() < 0.0625
        critical = 2.0 if is_critical else 1.0
        
        # Calculate final damage using improved formula
        level_factor = (2 * self.level / 5 + 2)
        damage = int(((level_factor * move['power'] * attack / defense) / 50 + 2) * stab * type_effectiveness * random_factor * critical)
        
        return max(1, damage), is_critical  # Minimum 1 damage
    
    def use_move(self, move: Dict, target: 'BattlePokemon') -> Dict:
        """Use a move and return the result with improved messaging"""
        # Check accuracy with improved miss system
        accuracy_roll = random.random() * 100
        if accuracy_roll > move['accuracy']:
            return {
                'success': False,
                'message': f"{self.name} used {move['name']}... but it missed!",
                'damage': 0
            }
        
        # Calculate damage
        damage, is_critical = self.calculate_damage(move, target)
        
        # Apply damage
        fainted = target.take_damage(damage)
        
        # Create descriptive battle message
        battle_message = f"{self.name} used {move['name']}. Dealt {damage} damage."
        
        # Add type effectiveness message
        type_message = ""
        if move['type'] in TYPE_EFFECTIVENESS and target.rarity in TYPE_EFFECTIVENESS[move['type']]:
            effectiveness = TYPE_EFFECTIVENESS[move['type']][target.rarity]
            if effectiveness == 2.0:
                type_message = " It's super effective!"
            elif effectiveness == 0.5:
                type_message = " It's not very effective..."
            elif effectiveness == 0.0:
                type_message = " It had no effect!"
        
        # Apply status effects (simplified)
        status_effect = ""
        if move['effect'] and "burn" in move['effect'].lower() and random.random() < 0.1:
            status_effect = f" {target.name} was burned!"
        elif move['effect'] and "paralyze" in move['effect'].lower() and random.random() < 0.1:
            status_effect = f" {target.name} was paralyzed!"
        elif move['effect'] and "freeze" in move['effect'].lower() and random.random() < 0.1:
            status_effect = f" {target.name} was frozen!"
        
        # Apply stat changes for status moves
        if move['power'] == 0:
            if "ATK" in move['effect']:
                target.stat_modifiers['atk'] = max(-6, target.stat_modifiers['atk'] - 1)
                status_effect = f" {target.name}'s Attack fell!"
            elif "DEF" in move['effect']:
                target.stat_modifiers['def'] = max(-6, target.stat_modifiers['def'] - 1)
                status_effect = f" {target.name}'s Defense fell!"
        
        # Add critical hit message
        critical_message = ""
        if is_critical:
            critical_message = " Critical hit!"
        
        # Add fainted message
        fainted_message = ""
        if fainted:
            fainted_message = f" {target.name} fainted!"
        
        final_message = battle_message + type_message + critical_message + status_effect + fainted_message
        
        return {
            'success': True,
            'message': final_message,
            'damage': damage,
            'fainted': fainted
        }

class Battle:
    """Represents a battle between two players"""
    
    def __init__(self, challenger_id: int, opponent_id: int, chat_id: int):
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.chat_id = chat_id
        self.battle_id = f"{challenger_id}_{opponent_id}_{int(datetime.now().timestamp())}"
        
        # Battle state
        self.status = "pending"  # pending, active, finished, waiting_for_switch
        self.challenger_team = []
        self.opponent_team = []
        self.current_round = 0
        self.battle_log = []
        self.created_at = datetime.now()
        
        # Turn management
        self.current_turn = "challenger"  # challenger or opponent
        self.turn_timeout = None
        
        # UI management
        self.battle_message_id = None
        self.current_turn_user_id = challenger_id
        
        # Pokemon switching state
        self.waiting_for_switch_user_id = None
        self.fainted_pokemon_name = None
        
        # Active Pokemon tracking
        self.challenger_active_pokemon_index = 0
        self.opponent_active_pokemon_index = 0
        
        # Run (forfeit) tracking
        self.run_votes = set()  # user_ids who pressed Run
    
    async def initialize_teams(self):
        """Initialize both players' teams"""
        # Ensure team table exists
        await TeamManager.ensure_team_table()
        
        # Get challenger's team
        challenger_team_data = await TeamManager.get_user_team(self.challenger_id)
        print(f"Challenger team data: {challenger_team_data}")
        if challenger_team_data and challenger_team_data['pokemon_ids']:
            challenger_pokemon = await self._get_pokemon_details(challenger_team_data['pokemon_ids'])
            print(f"Challenger pokemon details: {challenger_pokemon}")
            self.challenger_team = [BattlePokemon(pokemon) for pokemon in challenger_pokemon]
        
        # Get opponent's team
        opponent_team_data = await TeamManager.get_user_team(self.opponent_id)
        print(f"Opponent team data: {opponent_team_data}")
        if opponent_team_data and opponent_team_data['pokemon_ids']:
            opponent_pokemon = await self._get_pokemon_details(opponent_team_data['pokemon_ids'])
            print(f"Opponent pokemon details: {opponent_pokemon}")
            self.opponent_team = [BattlePokemon(pokemon) for pokemon in opponent_pokemon]
    
    async def _get_pokemon_details(self, pokemon_ids: List[int]) -> List[Dict]:
        """Get detailed Pokemon information from database"""
        print(f"Getting Pokemon details for IDs: {pokemon_ids}")
        if not pokemon_ids:
            print("No Pokemon IDs provided")
            return []
        
        try:
            pool = get_postgres_pool()
            if not pool:
                print("No database pool available")
                return []
                
            async with pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT character_id, name, rarity, anime, img_url, file_id, is_video
                    FROM characters 
                    WHERE character_id = ANY($1::int[])
                    ORDER BY character_id
                ''', pokemon_ids)
                
                result = [dict(row) for row in rows]
                print(f"Found {len(result)} Pokemon in database")
                return result
        except Exception as e:
            print(f"Error getting Pokemon details: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def can_start_battle(self) -> bool:
        """Check if battle can start (both teams have Pokemon)"""
        challenger_has_team = len(self.challenger_team) > 0
        opponent_has_team = len(self.opponent_team) > 0
        status_ok = self.status == "pending"
        
        print(f"Can start battle check:")
        print(f"  Challenger team size: {len(self.challenger_team)}")
        print(f"  Opponent team size: {len(self.opponent_team)}")
        print(f"  Status: {self.status}")
        print(f"  Result: {challenger_has_team and opponent_has_team and status_ok}")
        
        return (challenger_has_team and opponent_has_team and status_ok)
    
    def start_battle(self):
        """Start the battle"""
        if not self.can_start_battle():
            return False
        
        self.status = "active"
        self.current_round = 1
        self.battle_log.append(f"🎯 Battle started! Round {self.current_round}")
        
        # Initialize active Pokemon indices to the first Pokemon in each team
        self.challenger_active_pokemon_index = 0
        self.opponent_active_pokemon_index = 0
        
        print(f"Battle started - Challenger active: {self.challenger_active_pokemon_index}, Opponent active: {self.opponent_active_pokemon_index}")
        return True
    
    def get_battle_status(self) -> str:
        """Get current battle status as text"""
        if self.status == "pending":
            return "⏳ Waiting for opponent to accept..."
        elif self.status == "active":
            return f"⚔️ Battle in progress - Round {self.current_round}"
        elif self.status == "finished":
            return "🏁 Battle finished"
        elif self.status == "waiting_for_switch":
            return f"⚔️ Waiting for {self.fainted_pokemon_name} to switch in!"
        return "❓ Unknown status"
    
    def get_winner(self) -> Optional[int]:
        """Get the winner's user ID if battle is finished"""
        if self.status != "finished":
            return None
        
        challenger_alive = any(pokemon.is_alive() for pokemon in self.challenger_team)
        opponent_alive = any(pokemon.is_alive() for pokemon in self.opponent_team)
        
        if challenger_alive and not opponent_alive:
            return self.challenger_id
        elif opponent_alive and not challenger_alive:
            return self.opponent_id
        else:
            return None  # Draw or battle not finished
    
    def execute_turn(self, attacker_team: List[BattlePokemon], defender_team: List[BattlePokemon], 
                     attacker_id: int, defender_id: int) -> Dict:
        """Execute a battle turn"""
        # Find first alive Pokemon for each team
        attacker_pokemon = next((p for p in attacker_team if p.is_alive()), None)
        defender_pokemon = next((p for p in defender_team if p.is_alive()), None)
        
        if not attacker_pokemon or not defender_pokemon:
            return {'error': 'No alive Pokemon found'}
        
        # Select a random move
        move = random.choice(attacker_pokemon.moves)
        
        # Use the move
        result = attacker_pokemon.use_move(move, defender_pokemon)
        
        # Add to battle log
        self.battle_log.append(result['message'])
        
        # Check if defender fainted
        if result.get('fainted', False):
            self.battle_log.append(f"{defender_pokemon.name} fainted!")
            self.fainted_pokemon_name = defender_pokemon.name
            self.waiting_for_switch_user_id = defender_id # The user whose Pokemon fainted is the one to switch
        
        # Check if battle is over
        challenger_alive = any(p.is_alive() for p in self.challenger_team)
        opponent_alive = any(p.is_alive() for p in self.opponent_team)
        
        if not challenger_alive or not opponent_alive:
            self.status = "finished"
            if not challenger_alive:
                self.winner_id = self.opponent_id
            else:
                self.winner_id = self.challenger_id
            self.finished_at = datetime.now()
        
        return result
    
    async def get_battle_ui(self, current_turn_user_id: int, client: Client = None) -> tuple[str, InlineKeyboardMarkup]:
        """Get the battle UI with current state and move buttons"""
        print(f"Getting battle UI for user: {current_turn_user_id}")
        print(f"Challenger team size: {len(self.challenger_team)}")
        print(f"Opponent team size: {len(self.opponent_team)}")
        
        # Get active Pokemon using indices
        challenger_pokemon = None
        opponent_pokemon = None
        
        if self.challenger_active_pokemon_index < len(self.challenger_team):
            challenger_pokemon = self.challenger_team[self.challenger_active_pokemon_index]
        
        if self.opponent_active_pokemon_index < len(self.opponent_team):
            opponent_pokemon = self.opponent_team[self.opponent_active_pokemon_index]
        
        print(f"Challenger pokemon alive: {challenger_pokemon is not None and challenger_pokemon.is_alive()}")
        print(f"Opponent pokemon alive: {opponent_pokemon is not None and opponent_pokemon.is_alive()}")
        
        if not challenger_pokemon or not opponent_pokemon:
            print("No Pokemon found, returning battle ended message")
            return "Battle ended!", InlineKeyboardMarkup([])
        
        if not challenger_pokemon.is_alive() or not opponent_pokemon.is_alive():
            print("One or both Pokemon are fainted, returning battle ended message")
            return "Battle ended!", InlineKeyboardMarkup([])
        
        # Determine whose turn it is
        is_challenger_turn = current_turn_user_id == self.challenger_id
        current_pokemon = challenger_pokemon if is_challenger_turn else opponent_pokemon
        opponent_pokemon_display = opponent_pokemon if is_challenger_turn else challenger_pokemon
        
        # Create battle UI text without round number
        battle_text = ""
        
        # Show opponent Pokemon with improved formatting
        opponent_hp_bar = self._create_hp_bar(opponent_pokemon_display.current_hp, opponent_pokemon_display.max_hp)
        opponent_hp_percentage = int((opponent_pokemon_display.current_hp / opponent_pokemon_display.max_hp) * 100)
        
        battle_text += f"<b>Opponent's {opponent_pokemon_display.name} [{opponent_pokemon_display.rarity}]</b>\n"
        battle_text += f"Lv. 100 • HP {opponent_pokemon_display.current_hp}/{opponent_pokemon_display.max_hp} ({opponent_hp_percentage}%)\n"
        battle_text += f"{opponent_hp_bar}\n\n"
        
        # Show current turn indicator with actual user name as hyperlink
        turn_name = "Unknown"
        if client:
            try:
                user = await client.get_users(current_turn_user_id)
                turn_name = user.first_name or "Unknown"
                # Create hyperlink to user
                turn_name = f'<a href="tg://user?id={current_turn_user_id}">{turn_name}</a>'
            except:
                turn_name = f"User {current_turn_user_id}"
        else:
            turn_name = "Challenger" if is_challenger_turn else "Opponent"
        
        battle_text += f"<b>Current turn: {turn_name}</b>\n"
        
        # Show current Pokemon with improved formatting
        current_hp_bar = self._create_hp_bar(current_pokemon.current_hp, current_pokemon.max_hp)
        current_hp_percentage = int((current_pokemon.current_hp / current_pokemon.max_hp) * 100)
        
        battle_text += f"<b>{current_pokemon.name} [{current_pokemon.rarity}]</b>\n"
        battle_text += f"Lv. 100 • HP {current_pokemon.current_hp}/{current_pokemon.max_hp} ({current_hp_percentage}%)\n"
        battle_text += f"{current_hp_bar}\n\n"
        
        # Show moves with improved formatting
        battle_text += "<b>Available Moves:</b>\n"
        for i, move in enumerate(current_pokemon.moves, 1):
            # Add move type emoji
            type_emoji = self._get_type_emoji(move['type'])
            battle_text += f"{i}. <b>{move['name']}</b> {type_emoji} [{move['type']}]\n"
            battle_text += f"   Power: {move['power']:>3} | Accuracy: {move['accuracy']:>3}% | {move['effect']}\n"
        
        # Create move buttons with encoded battle ID to avoid underscore issues
        keyboard = []
        encoded_battle_id = self.battle_id.replace("_", "-")
        for i, move in enumerate(current_pokemon.moves, 1):
            type_emoji = self._get_type_emoji(move['type'])
            keyboard.append([InlineKeyboardButton(
                f"{type_emoji} {move['name']} ({move['power']})", 
                callback_data=f"use_move_{encoded_battle_id}_{i-1}"
            )])
        
        # Add Run button as the last row
        keyboard.append([InlineKeyboardButton("🏃 Run", callback_data=f"run_battle_{encoded_battle_id}")])
        
        return battle_text, InlineKeyboardMarkup(keyboard)
    
    async def get_switch_pokemon_ui(self, user_id: int, client: Client = None) -> tuple[str, InlineKeyboardMarkup]:
        """Get the Pokemon switching UI when a Pokemon faints"""
        # Determine which team the user is on
        if user_id == self.challenger_id:
            user_team = self.challenger_team
            opponent_team = self.opponent_team
        else:
            user_team = self.opponent_team
            opponent_team = self.challenger_team
        
        # Find opponent's Pokemon (the one that's still alive)
        opponent_pokemon = next((p for p in opponent_team if p.is_alive()), None)
        
        if not opponent_pokemon:
            return "Battle ended!", InlineKeyboardMarkup([])
        
        # Create switching UI text
        switch_text = ""
        
        # Show opponent Pokemon
        opponent_hp_bar = self._create_hp_bar(opponent_pokemon.current_hp, opponent_pokemon.max_hp)
        opponent_hp_percentage = int((opponent_pokemon.current_hp / opponent_pokemon.max_hp) * 100)
        
        switch_text += f"<b>Opponent's {opponent_pokemon.name} [{opponent_pokemon.rarity}]</b>\n"
        switch_text += f"Lv. 100 • HP {opponent_pokemon.current_hp}/{opponent_pokemon.max_hp} ({opponent_hp_percentage}%)\n"
        switch_text += f"{opponent_hp_bar}\n\n"
        
        # Show the fainted Pokemon (not the next alive one)
        switch_text += f"<b>{self.fainted_pokemon_name} [Fainted]</b>\n"
        switch_text += f"Lv. 100 • HP 0/0 (0%)\n"
        switch_text += f"▒▒▒▒▒▒▒▒▒▒▒\n\n"
        
        # Add switching message
        switch_text += "<b>Choose your next Pokemon.</b>\n"
        
        # Create switching buttons
        keyboard = []
        
        # View Team button (first row)
        keyboard.append([InlineKeyboardButton("👥 View Team", callback_data=f"view_team_{self.battle_id.replace('_', '-')}")])
        
        # Pokemon selection buttons (3x2 grid)
        pokemon_row = []
        for i, pokemon in enumerate(user_team, 1):
            if pokemon.is_alive():
                button_text = f"Pokemon {i} ✅"
            else:
                button_text = f"Pokemon {i} ❌"
            
            pokemon_row.append(InlineKeyboardButton(
                button_text, 
                callback_data=f"switch_pokemon_{self.battle_id.replace('_', '-')}_{i-1}"
            ))
            
            # Create 2 columns (3 buttons per row)
            if len(pokemon_row) == 2:
                keyboard.append(pokemon_row)
                pokemon_row = []
        
        # Add any remaining buttons
        if pokemon_row:
            keyboard.append(pokemon_row)
        
        return switch_text, InlineKeyboardMarkup(keyboard)
    
    async def get_team_view_ui(self, user_id: int, client: Client = None) -> tuple[str, InlineKeyboardMarkup]:
        """Get the team view UI showing all Pokemon in the team"""
        # Determine which team the user is on
        if user_id == self.challenger_id:
            user_team = self.challenger_team
        else:
            user_team = self.opponent_team
        
        # Create team view text
        team_text = "<b>🏆 Your Team</b>\n\n"
        
        for i, pokemon in enumerate(user_team, 1):
            if pokemon.is_alive():
                status = "✅ Alive"
                hp_info = f"HP {pokemon.current_hp}/{pokemon.max_hp}"
            else:
                status = "❌ Fainted"
                hp_info = "HP 0/0"
            
            team_text += f"<b>{i}. {pokemon.name} [{pokemon.rarity}]</b>\n"
            team_text += f"   {status} • {hp_info}\n\n"
        
        team_text += "<b>Choose your next Pokemon:</b>\n"
        
        # Create team view buttons
        keyboard = []
        
        # Back to switch UI button
        keyboard.append([InlineKeyboardButton("🔙 Back to Switch", callback_data=f"back_to_switch_{self.battle_id.replace('_', '-')}")])
        
        # Pokemon selection buttons (3x2 grid)
        pokemon_row = []
        for i, pokemon in enumerate(user_team, 1):
            if pokemon.is_alive():
                button_text = f"Pokemon {i} ✅"
            else:
                button_text = f"Pokemon {i} ❌"
            
            pokemon_row.append(InlineKeyboardButton(
                button_text, 
                callback_data=f"switch_pokemon_{self.battle_id.replace('_', '-')}_{i-1}"
            ))
            
            # Create 2 columns (3 buttons per row)
            if len(pokemon_row) == 2:
                keyboard.append(pokemon_row)
                pokemon_row = []
        
        # Add any remaining buttons
        if pokemon_row:
            keyboard.append(pokemon_row)
        
        return team_text, InlineKeyboardMarkup(keyboard)
    
    def _get_type_emoji(self, move_type: str) -> str:
        """Get emoji for move type"""
        type_emojis = {
            "Normal": "⚪",
            "Fire": "🔥",
            "Water": "💧",
            "Electric": "⚡",
            "Grass": "🌱",
            "Ice": "❄️",
            "Fighting": "👊",
            "Poison": "☠️",
            "Ground": "🌍",
            "Flying": "🦅",
            "Psychic": "🔮",
            "Bug": "🐛",
            "Rock": "🪨",
            "Ghost": "👻",
            "Dragon": "🐉",
            "Dark": "🌑",
            "Steel": "⚙️",
            "Fairy": "🧚"
        }
        return type_emojis.get(move_type, "⚪")
    
    def _create_hp_bar(self, current_hp: int, max_hp: int) -> str:
        """Create a visual HP bar with color coding"""
        if max_hp <= 0:
            return "███████████"
        
        percentage = current_hp / max_hp
        filled_bars = int(percentage * 11)  # 11 bars total
        empty_bars = 11 - filled_bars
        
        # Color code based on HP percentage
        if percentage > 0.6:
            bar_char = "█"  # Green for high HP
        elif percentage > 0.3:
            bar_char = "▓"  # Yellow for medium HP
        else:
            bar_char = "▒"  # Red for low HP
        
        return bar_char * filled_bars + "░" * empty_bars
    


class BattleManager:
    """Manages all battles in the system"""
    
    def __init__(self):
        self.active_battles = {}  # battle_id -> Battle
        self.pending_challenges = {}  # opponent_id -> challenger_id
        self.battle_timeouts = {}  # battle_id -> timeout_task
    
    async def create_challenge(self, challenger_id: int, opponent_id: int, chat_id: int) -> Optional[str]:
        """Create a battle challenge"""
        if opponent_id == challenger_id:
            return None  # Can't challenge yourself
        
        if opponent_id in self.pending_challenges:
            return None  # Already has a pending challenge
        
        # Check token requirements (20K minimum)
        try:
            pool = get_postgres_pool()
            if not pool:
                return "no_database"
                
            async with pool.acquire() as conn:
                # Check challenger's wallet
                challenger_row = await conn.fetchrow('SELECT wallet FROM users WHERE user_id = $1', challenger_id)
                if not challenger_row or challenger_row['wallet'] < 20000:
                    return "challenger_insufficient_tokens"
                
                # Check opponent's wallet
                opponent_row = await conn.fetchrow('SELECT wallet FROM users WHERE user_id = $1', opponent_id)
                if not opponent_row or opponent_row['wallet'] < 20000:
                    return "opponent_insufficient_tokens"
        except Exception as e:
            print(f"Error checking token requirements: {e}")
            return "database_error"
        
        # Ensure team table exists
        await TeamManager.ensure_team_table()
        
        # Check if both users have teams
        challenger_team = await TeamManager.get_user_team(challenger_id)
        opponent_team = await TeamManager.get_user_team(opponent_id)
        
        print(f"Creating challenge - Challenger team: {challenger_team}")
        print(f"Creating challenge - Opponent team: {opponent_team}")
        
        if not challenger_team or not challenger_team['pokemon_ids']:
            return None  # Challenger has no team
        
        if not opponent_team or not opponent_team['pokemon_ids']:
            return None  # Opponent has no team
        
        # Create challenge
        self.pending_challenges[opponent_id] = challenger_id
        
        # Set timeout for challenge
        asyncio.create_task(self._challenge_timeout(opponent_id))
        
        return "challenge_created"
    
    async def accept_challenge(self, opponent_id: int) -> Optional[Battle]:
        """Accept a battle challenge"""
        if opponent_id not in self.pending_challenges:
            return None  # No pending challenge
        
        challenger_id = self.pending_challenges.pop(opponent_id)
        
        # Re-check token requirements when accepting (in case balance changed)
        try:
            pool = get_postgres_pool()
            if not pool:
                return None
                
            async with pool.acquire() as conn:
                # Check challenger's wallet
                challenger_row = await conn.fetchrow('SELECT wallet FROM users WHERE user_id = $1', challenger_id)
                if not challenger_row or challenger_row['wallet'] < 20000:
                    return None  # Challenger no longer has enough tokens
                
                # Check opponent's wallet
                opponent_row = await conn.fetchrow('SELECT wallet FROM users WHERE user_id = $1', opponent_id)
                if not opponent_row or opponent_row['wallet'] < 20000:
                    return None  # Opponent no longer has enough tokens
        except Exception as e:
            print(f"Error checking token requirements during accept: {e}")
            return None
        
        # Create battle
        battle = Battle(challenger_id, opponent_id, 0)  # chat_id will be set when battle starts
        await battle.initialize_teams()
        
        if battle.can_start_battle():
            battle.start_battle()
            self.active_battles[battle.battle_id] = battle
            return battle
        
        return None
    
    async def decline_challenge(self, opponent_id: int) -> bool:
        """Decline a battle challenge"""
        if opponent_id in self.pending_challenges:
            challenger_id = self.pending_challenges.pop(opponent_id)
            return True
        return False
    
    async def _challenge_timeout(self, opponent_id: int):
        """Handle challenge timeout"""
        await asyncio.sleep(60)  # 1 minute timeout
        if opponent_id in self.pending_challenges:
            self.pending_challenges.pop(opponent_id)
    
    def get_pending_challenge(self, opponent_id: int) -> Optional[int]:
        """Get pending challenge for a user"""
        return self.pending_challenges.get(opponent_id)
    
    def get_active_battle(self, user_id: int) -> Optional[Battle]:
        """Get active battle for a user"""
        # Clean up any finished battles first
        self._cleanup_finished_battles()
        
        for battle in self.active_battles.values():
            if battle.challenger_id == user_id or battle.opponent_id == user_id:
                return battle
        return None
    
    def _cleanup_finished_battles(self):
        """Remove any finished battles from active battles"""
        finished_battles = []
        for battle_id, battle in self.active_battles.items():
            if battle.status == "finished":
                finished_battles.append(battle_id)
        
        for battle_id in finished_battles:
            del self.active_battles[battle_id]
            print(f"Cleaned up finished battle: {battle_id}")
    
    async def start_automated_battle(self, battle: Battle) -> bool:
        """Start an automated battle that runs to completion"""
        if battle.status != "active":
            return False
        
        try:
            # Run the battle automatically
            while battle.status == "active":
                # Execute challenger's turn
                if any(p.is_alive() for p in battle.challenger_team):
                    battle.execute_turn(battle.challenger_team, battle.opponent_team, 
                                     battle.challenger_id, battle.opponent_id)
                
                # Check if battle is over
                if battle.status == "finished":
                    break
                
                # Execute opponent's turn
                if any(p.is_alive() for p in battle.opponent_team):
                    battle.execute_turn(battle.opponent_team, battle.challenger_team, 
                                     battle.opponent_id, battle.challenger_id)
                
                # Check if battle is over
                if battle.status == "finished":
                    break
                
                # Increment round
                battle.current_round += 1
                
                # Add a small delay to make the battle readable
                await asyncio.sleep(1)
            
            return True
            
        except Exception as e:
            print(f"Error in automated battle: {e}")
            return False
    
    async def start_interactive_battle(self, battle: Battle, client: Client, chat_id: int) -> bool:
        """Start an interactive battle with UI"""
        print(f"Starting interactive battle for battle ID: {battle.battle_id}")
        print(f"Battle status: {battle.status}")
        
        if battle.status != "active":
            print(f"Battle status is not active: {battle.status}")
            return False
        
        try:
            # Send initial battle UI
            battle_text, keyboard = await battle.get_battle_ui(battle.challenger_id, client)
            
            # Add speed advantage message only at battle start
            challenger_pokemon = next((p for p in battle.challenger_team if p.is_alive()), None)
            opponent_pokemon = next((p for p in battle.opponent_team if p.is_alive()), None)
            
            speed_message = ""
            if challenger_pokemon and opponent_pokemon:
                challenger_speed = challenger_pokemon.get_effective_stats()['spd']
                opponent_speed = opponent_pokemon.get_effective_stats()['spd']
                
                if challenger_speed > opponent_speed:
                    speed_message = f"<i>{challenger_pokemon.name}'s speed advantage allows it to move first.</i>\n\n"
                elif opponent_speed > challenger_speed:
                    speed_message = f"<i>{opponent_pokemon.name}'s speed advantage allows it to move first.</i>\n\n"
                else:
                    speed_message = f"<i>Both Pokemon have equal speed!</i>\n\n"
            
            battle_text = "⚔️ <b>Battle begins!</b>\n\n" + speed_message + battle_text
            
            print(f"Battle UI generated successfully")
            print(f"Battle text length: {len(battle_text)}")
            print(f"Keyboard buttons: {len(keyboard.inline_keyboard) if keyboard.inline_keyboard else 0}")
            
            # Send the battle message
            battle_message = await client.send_message(chat_id, battle_text, reply_markup=keyboard)
            battle.battle_message_id = battle_message.id
            battle.chat_id = chat_id
            
            print(f"Battle message sent successfully with ID: {battle_message.id}")
            return True
            
        except Exception as e:
            print(f"Error starting interactive battle: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def execute_move(self, battle: Battle, move_index: int, user_id: int, client: Client):
        """Execute a move in the battle with improved messaging"""
        try:
            # Determine which team the user is on
            if user_id == battle.challenger_id:
                attacker_team = battle.challenger_team
                defender_team = battle.opponent_team
                next_turn_user_id = battle.opponent_id
                attacker_pokemon = battle.challenger_team[battle.challenger_active_pokemon_index]
                defender_pokemon = battle.opponent_team[battle.opponent_active_pokemon_index]
            else:
                attacker_team = battle.opponent_team
                defender_team = battle.challenger_team
                next_turn_user_id = battle.challenger_id
                attacker_pokemon = battle.opponent_team[battle.opponent_active_pokemon_index]
                defender_pokemon = battle.challenger_team[battle.challenger_active_pokemon_index]
            
            # Check if Pokemon are alive
            if not attacker_pokemon.is_alive() or not defender_pokemon.is_alive():
                return
            
            # Get the move
            if move_index >= len(attacker_pokemon.moves):
                return
            
            move = attacker_pokemon.moves[move_index]
            
            # Execute the move
            result = attacker_pokemon.use_move(move, defender_pokemon)
            
            # Add to battle log with improved formatting
            battle.battle_log.append(result['message'])
            
            # Check if defender fainted
            if result.get('fainted', False):
                battle.fainted_pokemon_name = defender_pokemon.name
                battle.waiting_for_switch_user_id = next_turn_user_id
                
                # Check if the user has any alive Pokemon left
                alive_pokemon_count = sum(1 for p in defender_team if p.is_alive())
                
                if alive_pokemon_count == 0:
                    # No Pokemon left, battle is over
                    battle.status = "finished"
                    battle.winner_id = user_id
                    battle.finished_at = datetime.now()
                    
                    # Remove battle from active battles
                    if battle.battle_id in self.active_battles:
                        del self.active_battles[battle.battle_id]
                        print(f"Battle {battle.battle_id} removed from active battles")
                    
                    # Show battle results
                    await self.show_battle_results(battle, client)
                    return
                else:
                    # Pokemon fainted but user has more Pokemon, show switching UI
                    battle.status = "waiting_for_switch"
                    switch_text, switch_keyboard = await battle.get_switch_pokemon_ui(next_turn_user_id, client)
                    
                    # Add the move result message at the top
                    if result.get('success', False):
                        result_message = f"<b>⚡ {result['message']}</b>\n\n"
                    else:
                        result_message = f"<b>💨 {result['message']}</b>\n\n"
                    
                    switch_text = result_message + switch_text
                    
                    await client.edit_message_text(
                        battle.chat_id,
                        battle.battle_message_id,
                        switch_text,
                        reply_markup=switch_keyboard
                    )
                    return
            
            # Update turn
            battle.current_turn_user_id = next_turn_user_id
            battle.current_round += 1
            
            # Update battle UI with move result
            await self.update_battle_ui_with_move_result(battle, client, result)
            
        except Exception as e:
            print(f"Error executing move: {e}")
            import traceback
            traceback.print_exc()
    
    async def update_battle_ui_with_move_result(self, battle: Battle, client: Client, move_result: Dict):
        """Update the battle UI message with move result"""
        try:
            battle_text, keyboard = await battle.get_battle_ui(battle.current_turn_user_id, client)
            
            # Add the move result message at the top
            if move_result.get('success', False):
                result_message = f"<b>⚡ {move_result['message']}</b>\n\n"
            else:
                result_message = f"<b>💨 {move_result['message']}</b>\n\n"
            
            battle_text = result_message + battle_text
            
            await client.edit_message_text(
                battle.chat_id,
                battle.battle_message_id,
                battle_text,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Error updating battle UI with move result: {e}")
            import traceback
            traceback.print_exc()
    
    async def show_battle_results(self, battle: Battle, client: Client):
        """Show battle results with improved formatting"""
        try:
            winner_id = battle.get_winner()
            if winner_id:
                try:
                    winner_user = await client.get_users(winner_id)
                    winner_name = winner_user.first_name or "Unknown"
                    winner_username = winner_user.username or f"user{winner_id}"
                    
                    # Get loser info
                    loser_id = battle.opponent_id if winner_id == battle.challenger_id else battle.challenger_id
                    try:
                        loser_user = await client.get_users(loser_id)
                        loser_name = loser_user.first_name or "Unknown"
                        loser_username = loser_user.username or f"user{loser_id}"
                    except:
                        loser_name = f"User {loser_id}"
                        loser_username = f"user{loser_id}"
                except:
                    winner_name = f"User {winner_id}"
                    winner_username = f"user{winner_id}"
                    loser_name = "Unknown"
                    loser_username = "unknown"
                
                # Calculate battle statistics
                total_rounds = battle.current_round
                battle_duration = battle.finished_at - battle.created_at
                duration_seconds = int(battle_duration.total_seconds())
                
                # Count total damage dealt
                total_damage = 0
                for log_entry in battle.battle_log:
                    if "Dealt" in log_entry:
                        try:
                            damage_part = log_entry.split("Dealt ")[1].split(" ")[0]
                            total_damage += int(damage_part)
                        except:
                            pass
                
                # Process rewards
                winner_reward_tokens = 50000
                winner_reward_shards = 5000
                loser_penalty_tokens = 8000
                
                # Update database with rewards
                try:
                    await self._give_rewards(winner_id, winner_reward_tokens, winner_reward_shards)
                    await self._deduct_tokens(loser_id, loser_penalty_tokens)
                except Exception as e:
                    print(f"Error processing rewards: {e}")
                
                result_text = (
                    f"🏆 <b>Battle Results</b> 🏆\n\n"
                    f"<b>Winner:</b> <a href='tg://user?id={winner_id}'>{winner_name}</a> 🎉\n"
                    f"<b>Loser:</b> <a href='tg://user?id={loser_id}'>{loser_name}</a> 😔\n"
                    f"💰 <b>Rewards:</b>\n"
                    f"• <a href='tg://user?id={winner_id}'>{winner_name}</a> earned: +{winner_reward_tokens:,} tokens, +{winner_reward_shards:,} shards\n"
                    f"• <a href='tg://user?id={loser_id}'>{loser_name}</a> lost: -{loser_penalty_tokens:,} tokens\n\n"
                )
                
                await client.edit_message_text(
                    battle.chat_id,
                    battle.battle_message_id,
                    result_text,
                    disable_web_page_preview=True
                )
            else:
                await client.edit_message_text(
                    battle.chat_id,
                    battle.battle_message_id,
                    "🤝 <b>Battle Results</b> 🤝\n\nIt was a draw! Both trainers fought valiantly!"
                )
            
            # Ensure battle is removed from active battles
            if battle.battle_id in self.active_battles:
                del self.active_battles[battle.battle_id]
                print(f"Battle {battle.battle_id} removed from active battles in show_battle_results")
                
        except Exception as e:
            print(f"Error showing battle results: {e}")
            import traceback
            traceback.print_exc()
            # Still try to remove the battle even if showing results fails
            if battle.battle_id in self.active_battles:
                del self.active_battles[battle.battle_id]
                print(f"Battle {battle.battle_id} removed from active battles after error")
    
    def get_battle_history(self, user_id: int, limit: int = 5) -> List[Dict]:
        """Get battle history for a user"""
        # This would typically query the database
        # For now, return empty list
        return []
    
    def clear_all_battles(self):
        """Clear all active battles (for debugging/testing)"""
        count = len(self.active_battles)
        self.active_battles.clear()
        self.pending_challenges.clear()
        print(f"Cleared {count} active battles and all pending challenges")
        return count
    
    async def _give_rewards(self, user_id: int, tokens: int, shards: int):
        """Give rewards to the winner"""
        try:
            pool = get_postgres_pool()
            if not pool:
                print("No database pool available for rewards")
                return
                
            async with pool.acquire() as conn:
                # Update wallet (tokens)
                await conn.execute('''
                    UPDATE users 
                    SET wallet = wallet + $1 
                    WHERE user_id = $2
                ''', tokens, user_id)
                
                # Update shards
                await conn.execute('''
                    UPDATE users 
                    SET shards = shards + $1 
                    WHERE user_id = $2
                ''', shards, user_id)
                
                print(f"Gave {tokens} tokens and {shards} shards to user {user_id}")
        except Exception as e:
            print(f"Error giving rewards: {e}")
    
    async def _deduct_tokens(self, user_id: int, tokens: int):
        """Deduct tokens from the loser"""
        try:
            pool = get_postgres_pool()
            if not pool:
                print("No database pool available for token deduction")
                return
                
            async with pool.acquire() as conn:
                # Update wallet (ensure it doesn't go below 0)
                await conn.execute('''
                    UPDATE users 
                    SET wallet = GREATEST(0, wallet - $1) 
                    WHERE user_id = $2
                ''', tokens, user_id)
                
                print(f"Deducted {tokens} tokens from user {user_id}")
        except Exception as e:
            print(f"Error deducting tokens: {e}")
    
    async def execute_pokemon_switch(self, battle: Battle, pokemon_index: int, user_id: int, client: Client):
        """Execute a Pokemon switch and resume the battle"""
        try:
            print(f"Executing Pokemon switch - User: {user_id}, Pokemon index: {pokemon_index}")
            
            # Determine which team the user is on
            if user_id == battle.challenger_id:
                user_team = battle.challenger_team
                opponent_team = battle.opponent_team
                active_index_field = "challenger_active_pokemon_index"
            else:
                user_team = battle.opponent_team
                opponent_team = battle.challenger_team
                active_index_field = "opponent_active_pokemon_index"
            
            print(f"User team size: {len(user_team)}, Active index field: {active_index_field}")
            
            # Check if pokemon index is valid
            if pokemon_index < 0 or pokemon_index >= len(user_team):
                print(f"Invalid Pokemon index: {pokemon_index}")
                return
            
            # Get the selected Pokemon
            selected_pokemon = user_team[pokemon_index]
            print(f"Selected Pokemon: {selected_pokemon.name}, Alive: {selected_pokemon.is_alive()}")
            
            # Check if the selected Pokemon is alive
            if not selected_pokemon.is_alive():
                print(f"Selected Pokemon {selected_pokemon.name} is not alive")
                return
            
            # Check if this Pokemon is already the active one
            current_active_index = getattr(battle, active_index_field)
            print(f"Current active index: {current_active_index}, Selected index: {pokemon_index}")
            if current_active_index == pokemon_index:
                print(f"Pokemon {selected_pokemon.name} is already active")
                return
            
            # Set the selected Pokemon as the active one
            setattr(battle, active_index_field, pokemon_index)
            print(f"Set {active_index_field} to {pokemon_index}")
            
            # Reset battle status
            battle.status = "active"
            battle.waiting_for_switch_user_id = None
            battle.fainted_pokemon_name = None
            
            # Update turn to the other player
            if user_id == battle.challenger_id:
                battle.current_turn_user_id = battle.opponent_id
            else:
                battle.current_turn_user_id = battle.challenger_id
            
            print(f"Updated turn to user: {battle.current_turn_user_id}")
            
            # Update battle UI with switch message and new battle state
            battle_text, keyboard = await battle.get_battle_ui(battle.current_turn_user_id, client)
            
            # Add the switch message at the top
            switch_message = f"<b>🔄 Switched to {selected_pokemon.name}!</b>\n\n"
            battle_text = switch_message + battle_text
            
            await client.edit_message_text(
                battle.chat_id,
                battle.battle_message_id,
                battle_text,
                reply_markup=keyboard
            )
            
            print(f"Successfully switched to {selected_pokemon.name}")
            
        except Exception as e:
            print(f"Error executing Pokemon switch: {e}")
            import traceback
            traceback.print_exc()
    

# Global battle manager instance
battle_manager = BattleManager()

# Command handlers
import html


def _user_link(u) -> str:
    """Safe HTML link to a user, falling back to tg:// deep link if no username."""
    name = html.escape(u.first_name or "Unknown")
    if u.username:
        href = f"https://t.me/{u.username}"
    else:
        href = f"tg://user?id={u.id}"
    return f"<a href='{href}'>{name}</a>"


@auto_register_user
async def battle_command(client: Client, message: Message):
    """Handle /battle command - challenge another user to battle"""
    challenger_id = message.from_user.id
    opponent_id = None
    opponent_user = None
    
    # Check if username is provided as argument
    args = message.text.split()
    if len(args) > 1:
        username = args[1].lstrip('@')  # Remove @ if present
        try:
            opponent_user = await client.get_users(username)
            opponent_id = opponent_user.id
        except Exception as e:
            await message.reply_text("❌ User not found! Please provide a valid username.")
            return
    # Check if replying to a message
    elif message.reply_to_message:
        opponent_user = message.reply_to_message.from_user
        opponent_id = opponent_user.id
    else:
        await message.reply_text(
            "<b>⚔️ Pokemon Battle Challenge</b>\n\n"
            "To challenge someone to a battle:\n"
            "• Reply to their message with: <code>/battle</code>\n"
            "• Or use: <code>/battle @username</code>\n\n"
            "<b>Requirements:</b>\n"
            "• Both players must have <b>20,000+ tokens</b> in their wallet\n"
            "• Both players must have a team of Pokemon\n\n"
            "Use <code>/team</code> to manage your team.\n"
            "Use <code>/balance</code> to check your token balance."
        )
        return
    
    if challenger_id == opponent_id:
        await message.reply_text("❌ You cannot challenge yourself to a battle!")
        return
    
    # Check if opponent is a bot
    if opponent_id < 0:
        await message.reply_text("❌ You cannot challenge a bot to a battle!")
        return
    
    # Check if challenger already has an active battle
    active_battle = battle_manager.get_active_battle(challenger_id)
    if active_battle:
        await message.reply_text("❌ You are already in an active battle!")
        return
    
    # Check if opponent already has an active battle
    active_battle = battle_manager.get_active_battle(opponent_id)
    if active_battle:
        await message.reply_text("❌ Your opponent is already in an active battle!")
        return
    
    # Check if there's already a pending challenge
    if battle_manager.get_pending_challenge(opponent_id):
        await message.reply_text("❌ This user already has a pending challenge!")
        return
    
    # Get user names (define these before the challenge creation to avoid scope issues)
    challenger_name = message.from_user.first_name or "Unknown"
    challenger_username = message.from_user.username or f"user{challenger_id}"
    opponent_name = opponent_user.first_name or "Unknown"
    opponent_username = opponent_user.username or f"user{opponent_id}"
    
    # Create challenge
    result = await battle_manager.create_challenge(challenger_id, opponent_id, message.chat.id)
    
    if result == "challenge_created":
        # Create challenge message with buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Accept Battle", callback_data=f"accept_battle_{challenger_id}"),
                InlineKeyboardButton("❌ Decline Battle", callback_data=f"decline_battle_{challenger_id}")
            ]
        ])
        
        challenge_text = (
            f"⚔️ <b>Pokemon Battle Challenge!</b>\n\n"
            f"<a href='https://t.me/{challenger_username}'>{challenger_name}</a> has challenged <a href='https://t.me/{opponent_username}'>{opponent_name}</a> to a Pokemon battle!\n\n"
            f"🎯 <b>Battle Format:</b> 3 vs 3 Pokemon\n"
            f"⚡️ <b>Battle Type:</b> Turn-based PvP\n"
            f"💰 <b>Rewards:</b> Winner gets 50K tokens + 5K shards, Loser loses 8K tokens\n"
            f"💸 <b>Entry Fee:</b> 20K tokens required (both users)\n"
            f"⏰ <b>Challenge expires in:</b> 1 minute\n\n"
            f"Click below to accept or decline the challenge!"
        )
        
        await client.send_message(message.chat.id, challenge_text, reply_markup=keyboard, disable_web_page_preview=True)
        
    elif result == "challenger_insufficient_tokens":
        await message.reply_text(
            "❌ <b>Insufficient Tokens!</b>\n\n"
            "You need at least <b>20,000 tokens</b> in your wallet to start a battle.\n"
            "Use <code>/balance</code> to check your current balance."
        )
    elif result == "opponent_insufficient_tokens":
        await message.reply_text(
            "❌ <b>Opponent Insufficient Tokens!</b>\n\n"
            f"<a href='tg://user?id={opponent_id}'>{opponent_name}</a> needs at least <b>20,000 tokens</b> in their wallet to participate in battles.\n"
            "They should use <code>/balance</code> to check their current balance."
        )
    elif result == "no_database":
        await message.reply_text("❌ <b>Database Error!</b>\n\nUnable to connect to the database. Please try again later.")
    elif result == "database_error":
        await message.reply_text("❌ <b>Database Error!</b>\n\nAn error occurred while checking token requirements. Please try again later.")
    else:
        await message.reply_text("❌ Failed to create battle challenge. Make sure both players have teams!")


@auto_register_user
async def battleinfo_command(client: Client, message: Message):
    """Handle /battleinfo command - show battle information and help"""
    help_text = (
        "<b>⚔️ Pokemon Battle System</b>\n\n"
        "<b>Commands:</b>\n"
        "• <code>/battle @username</code> - Challenge someone to battle\n"
        "• <code>/battle</code> - Challenge someone to battle (reply to their message)\n"
        "• <code>/battleinfo</code> - Show this help message\n"
        "• <code>/mybattle</code> - Show your current battle status\n\n"
        "<b>Battle Requirements:</b>\n"
        "• 💸 <b>20,000 tokens</b> minimum in wallet (both players)\n"
        "• 🎯 3 vs 3 Pokemon team\n"
        "• ⚡ Turn-based combat system\n\n"
        "<b>Battle Rewards:</b>\n"
        "• 🏆 <b>Winner:</b> +50,000 tokens, +5,000 shards\n"
        "• 😔 <b>Loser:</b> -8,000 tokens\n"
        "• ⏰ 1-minute challenge timeout\n\n"
        "<b>Pokemon Stats:</b>\n"
        "• <b>ATK:</b> Attack power\n"
        "• <b>SPE:</b> Special attack and speed\n"
        "• <b>HP:</b> Health points\n"
        "• <b>DEF:</b> Defense\n\n"
        "<b>Rarity Bonuses:</b>\n"
        "Higher rarity Pokemon have better stats and moves!\n\n"
        "Use <code>/team</code> to manage your battle team!\n"
        "Use <code>/balance</code> to check your token balance!"
    )
    
    await message.reply_text(help_text)

@auto_register_user
async def mybattle_command(client: Client, message: Message):
    """Handle /mybattle command - show user's current battle status"""
    user_id = message.from_user.id
    
    # Check for active battle
    active_battle = battle_manager.get_active_battle(user_id)
    if active_battle:
        battle_text = (
            f"⚔️ <b>Active Battle</b>\n\n"
            f"<b>Battle ID:</b> {active_battle.battle_id}\n"
            f"<b>Status:</b> {active_battle.get_battle_status()}\n"
            f"<b>Current Round:</b> {active_battle.current_round}\n"
            f"<b>Current Turn:</b> {active_battle.current_turn}\n\n"
        )
        
        if active_battle.challenger_id == user_id:
            opponent_id = active_battle.opponent_id
            battle_text += "<b>You are:</b> Challenger\n"
        else:
            opponent_id = active_battle.challenger_id
            battle_text += "<b>You are:</b> Opponent\n"
        
        # Get opponent name
        try:
            opponent_user = await client.get_users(opponent_id)
            opponent_name = opponent_user.first_name or "Unknown"
            opponent_username = opponent_user.username or f"user{opponent_id}"
            battle_text += f"<b>Opponent:</b> <a href='https://t.me/{opponent_username}'>{opponent_name}</a>\n"
        except:
            battle_text += f"<b>Opponent:</b> User {opponent_id}\n"
        
        await message.reply_text(battle_text)
        return
    
    # Check for pending challenge
    pending_challenge = battle_manager.get_pending_challenge(user_id)
    if pending_challenge:
        try:
            challenger_user = await client.get_users(pending_challenge)
            challenger_name = challenger_user.first_name or "Unknown"
            challenger_username = challenger_user.username or f"user{pending_challenge}"
            battle_text = (
                f"⏳ <b>Pending Challenge</b>\n\n"
                f"<a href='https://t.me/{challenger_username}'>{challenger_name}</a> has challenged you to a battle!\n"
                f"Check your recent messages to accept or decline."
            )
            await message.reply_text(battle_text, disable_web_page_preview=True)
            return
        except:
            pass
    
    # No active battle or challenge
    await message.reply_text(
        "⚔️ <b>No Active Battle</b>\n\n"
        "You are not currently in a battle.\n"
        "Use <code>/battle</code> to challenge someone, or wait for a challenge!"
    )

@auto_register_user
async def testteam_command(client: Client, message: Message):
    """Handle /testteam command - create a test team for battle testing"""
    user_id = message.from_user.id
    
    # Ensure team table exists
    await TeamManager.ensure_team_table()
    
    # Check if user already has a team
    existing_team = await TeamManager.get_user_team(user_id)
    if existing_team and existing_team['pokemon_ids']:
        await message.reply_text(
            "✅ <b>You already have a team!</b>\n\n"
            f"Team: {existing_team['team_name']}\n"
            f"Pokemon: {len(existing_team['pokemon_ids'])} Pokemon\n\n"
            "You can use <code>/battle</code> to challenge someone!"
        )
        return
    
    # Create a test team with some sample Pokemon IDs
    # These should be valid Pokemon IDs from your database
    test_pokemon_ids = [1, 2, 3]  # Valid Pokemon IDs: Bulbasaur, Ivysaur, Venusaur
    
    success = await TeamManager.create_or_update_team(user_id, test_pokemon_ids, "Test Team")
    
    if success:
        await message.reply_text(
            "✅ <b>Test team created!</b>\n\n"
            "A test team has been created for you.\n"
            "You can now use <code>/battle</code> to challenge someone!\n\n"
            "Note: This is a test team. In a real scenario, you would add your own Pokemon using <code>/addteam [pokemon_id]</code>"
        )
    else:
        await message.reply_text(
            "❌ <b>Failed to create test team!</b>\n\n"
            "Please try again or contact an administrator."
        )

@auto_register_user
async def clearbattles_command(client: Client, message: Message):
    """Handle /clearbattles command - clear all battles (admin/debug command)"""
    user_id = message.from_user.id
    
    # Only allow owner to clear battles
    from config import OWNER_ID
    if user_id != OWNER_ID:
        await message.reply_text("❌ Only the bot owner can use this command!")
        return
    
    count = battle_manager.clear_all_battles()
    await message.reply_text(f"✅ Cleared {count} active battles and all pending challenges!")

# Callback handlers
async def battle_callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle battle-related callback queries"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data.startswith("accept_battle_"):
        challenger_id = int(data.split("_")[2])
        
        # Check if this user is the one being challenged (opponent)
        if user_id == challenger_id:  # This was backwards - opponent should accept, not challenger
            await callback_query.answer("❌ You cannot accept your own challenge!", show_alert=True)
            return
        
        # Accept the challenge
        battle = await battle_manager.accept_challenge(user_id)
        
        if battle:
            # Start interactive battle immediately
            success = await battle_manager.start_interactive_battle(battle, client, callback_query.message.chat.id)
            
            if success:
                await callback_query.message.edit_text(
                    "⚔️ <b>Battle Accepted!</b>\n\n"
                    "The battle has started! Check the battle message below."
                )
                await callback_query.answer("✅ Battle started!", show_alert=True)
            else:
                await callback_query.answer("❌ Failed to start battle!", show_alert=True)
        else:
            # Check if it's a token issue
            try:
                pool = get_postgres_pool()
                if pool:
                    async with pool.acquire() as conn:
                        challenger_row = await conn.fetchrow('SELECT wallet FROM users WHERE user_id = $1', challenger_id)
                        opponent_row = await conn.fetchrow('SELECT wallet FROM users WHERE user_id = $1', user_id)
                        
                        if not challenger_row or challenger_row['wallet'] < 20000:
                            await callback_query.answer("❌ Challenger doesn't have enough tokens!", show_alert=True)
                            return
                        elif not opponent_row or opponent_row['wallet'] < 20000:
                            await callback_query.answer("❌ You don't have enough tokens! Need 20K+", show_alert=True)
                            return
            except:
                pass
            
            await callback_query.answer("❌ Failed to start battle! Check requirements.", show_alert=True)
    
    elif data.startswith("decline_battle_"):
        challenger_id = int(data.split("_")[2])
        
        # Check if this user is the one being challenged (opponent)
        if user_id == challenger_id:  # This was backwards - opponent should decline, not challenger
            await callback_query.answer("❌ You cannot decline your own challenge!", show_alert=True)
            return
        
        # Decline the challenge
        declined = await battle_manager.decline_challenge(user_id)
        
        if declined:
            await callback_query.message.edit_text(
                "❌ <b>Battle Challenge Declined</b>\n\n"
                "The battle challenge has been declined."
            )
            await callback_query.answer("❌ Battle declined!", show_alert=True)
        else:
            await callback_query.answer("❌ Failed to decline battle!", show_alert=True)
    

    
    elif data.startswith("use_move_"):
        # Parse move data: use_move_battle_id_move_index
        parts = data.split("_")
        encoded_battle_id = parts[2]
        move_index = int(parts[3])
        
        # Decode battle ID (replace dashes with underscores)
        battle_id = encoded_battle_id.replace("-", "_")
        
        battle = battle_manager.active_battles.get(battle_id)
        if not battle:
            await callback_query.answer("❌ Battle not found!", show_alert=True)
            return
        
        # Check if user is part of this battle
        if user_id not in [battle.challenger_id, battle.opponent_id]:
            await callback_query.answer("❌ You are not part of this battle!", show_alert=True)
            return
        
        # Check if it's user's turn
        if user_id != battle.current_turn_user_id:
            await callback_query.answer("❌ It's not your turn!", show_alert=True)
            return
        
        # Execute the move
        await battle_manager.execute_move(battle, move_index, user_id, client)
        
        await callback_query.answer("⚔️ Move executed!", show_alert=False)
    
    elif data.startswith("view_team_"):
        # Parse team view data: view_team_battle_id
        parts = data.split("_")
        encoded_battle_id = parts[2]
        battle_id = encoded_battle_id.replace("-", "_")
        
        battle = battle_manager.active_battles.get(battle_id)
        if not battle:
            await callback_query.answer("❌ Battle not found!", show_alert=True)
            return
        
        # Check if user is part of this battle
        if user_id not in [battle.challenger_id, battle.opponent_id]:
            await callback_query.answer("❌ You are not part of this battle!", show_alert=True)
            return
        
        # Check if user is the one who needs to switch
        if user_id != battle.waiting_for_switch_user_id:
            await callback_query.answer("❌ It's not your turn to switch!", show_alert=True)
            return
        
        # Create team view text for alert - only show Pokemon names
        team_text = "🏆 Your Team:\n\n"
        
        # Determine which team the user is on
        if user_id == battle.challenger_id:
            user_team = battle.challenger_team
        else:
            user_team = battle.opponent_team
        
        for i, pokemon in enumerate(user_team, 1):
            team_text += f"{i}. {pokemon.name}\n"
        
        team_text += "\nChoose your next Pokemon using the buttons below!"
        
        await callback_query.answer(team_text, show_alert=True)
    
    elif data.startswith("back_to_switch_"):
        # Parse back to switch data: back_to_switch_battle_id
        parts = data.split("_")
        encoded_battle_id = parts[3]
        battle_id = encoded_battle_id.replace("-", "_")
        
        battle = battle_manager.active_battles.get(battle_id)
        if not battle:
            await callback_query.answer("❌ Battle not found!", show_alert=True)
            return
        
        # Check if user is part of this battle
        if user_id not in [battle.challenger_id, battle.opponent_id]:
            await callback_query.answer("❌ You are not part of this battle!", show_alert=True)
            return
        
        # Check if user is the one who needs to switch
        if user_id != battle.waiting_for_switch_user_id:
            await callback_query.answer("❌ It's not your turn to switch!", show_alert=True)
            return
        
        # Show switch UI
        switch_text, switch_keyboard = await battle.get_switch_pokemon_ui(user_id, client)
        await client.edit_message_text(
            battle.chat_id,
            battle.battle_message_id,
            switch_text,
            reply_markup=switch_keyboard
        )
        await callback_query.answer("🔙 Back to switch!", show_alert=True)
    
    elif data.startswith("switch_pokemon_"):
        # Parse switch Pokemon data: switch_pokemon_battle_id_pokemon_index
        parts = data.split("_")
        encoded_battle_id = parts[2]
        pokemon_index = int(parts[3])
        battle_id = encoded_battle_id.replace("-", "_")
        
        battle = battle_manager.active_battles.get(battle_id)
        if not battle:
            await callback_query.answer("❌ Battle not found!", show_alert=True)
            return
        
        # Check if user is part of this battle
        if user_id not in [battle.challenger_id, battle.opponent_id]:
            await callback_query.answer("❌ You are not part of this battle!", show_alert=True)
            return
        
        # Check if user is the one who needs to switch
        if user_id != battle.waiting_for_switch_user_id:
            await callback_query.answer("❌ It's not your turn to switch!", show_alert=True)
            return
        
        # Execute the Pokemon switch
        await battle_manager.execute_pokemon_switch(battle, pokemon_index, user_id, client)
        
        await callback_query.answer("🔄 Pokemon switched!", show_alert=True)

    elif data.startswith("run_battle_"):
        # Parse: run_battle_battle_id
        parts = data.split("_")
        encoded_battle_id = parts[2]
        battle_id = encoded_battle_id.replace("-", "_")
        
        battle = battle_manager.active_battles.get(battle_id)
        if not battle:
            await callback_query.answer("❌ Battle not found!", show_alert=True)
            return
        
        # Ensure user is participant
        if user_id not in [battle.challenger_id, battle.opponent_id]:
            await callback_query.answer("❌ You are not part of this battle!", show_alert=True)
            return
        
        # Record the run vote
        battle.run_votes.add(user_id)
        
        # If both users voted to run, end battle immediately as mutual end
        if battle.challenger_id in battle.run_votes and battle.opponent_id in battle.run_votes:
            battle.status = "finished"
            battle.finished_at = datetime.now()
            # No winner/loser or token adjustments for mutual run
            try:
                challenger_user = await client.get_users(battle.challenger_id)
                challenger_name = challenger_user.first_name or "Unknown"
            except:
                challenger_name = f"User {battle.challenger_id}"
            try:
                opponent_user = await client.get_users(battle.opponent_id)
                opponent_name = opponent_user.first_name or "Unknown"
            except:
                opponent_name = f"User {battle.opponent_id}"
            end_text = (
                f"🤝 <b>Battle Ended</b> 🤝\n\n"
                f"<a href='tg://user?id={battle.challenger_id}'>{challenger_name}</a> & "
                f"<a href='tg://user?id={battle.opponent_id}'>{opponent_name}</a> both have decided to end this match here!!"
            )
            await client.edit_message_text(
                battle.chat_id,
                battle.battle_message_id,
                end_text,
                disable_web_page_preview=True
            )
            # Remove from active battles
            if battle.battle_id in battle_manager.active_battles:
                del battle_manager.active_battles[battle.battle_id]
            await callback_query.answer("🏁 Battle ended by mutual consent.", show_alert=True)
            return
        else:
            # Inform that this user voted to run, waiting for the other
            pending_user_id = battle.opponent_id if user_id == battle.challenger_id else battle.challenger_id
            waiter_text, keyboard = await battle.get_battle_ui(battle.current_turn_user_id, client)
            waiter_banner = (
                f"<b>🏃 Run requested.</b> Waiting for <a href='tg://user?id={pending_user_id}'>the other trainer</a> to confirm.\n\n"
            )
            await client.edit_message_text(
                battle.chat_id,
                battle.battle_message_id,
                waiter_banner + waiter_text,
                reply_markup=keyboard
            )
            await callback_query.answer("⏳ Waiting for the other trainer to Run.", show_alert=False)

def setup_battle_handlers(app: Client):
    """Register battle callback handlers"""
    print("Registering battle callback handlers...")
    
    # Register callback handlers
    app.on_callback_query(filters.regex(r"^(accept_battle_|decline_battle_|use_move_|view_team_|back_to_switch_|switch_pokemon_|run_battle_)"))(battle_callback_handler)
    
    print("Battle callback handlers registered successfully!")
    