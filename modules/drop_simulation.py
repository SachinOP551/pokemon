import asyncio
from datetime import datetime
import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.drop import DropManager
from modules.database import Database
import json

class DropSimulator:
    def __init__(self):
        self.db = Database()
        self.drop_manager = DropManager(self.db)
    
    async def calculate_expected_distribution(self, duration_hours=15, droptime=20):
        print(f"Calculating expected distribution for {duration_hours} hours with droptime {droptime}")
        
        # Calculate total messages and expected drops
        total_messages = duration_hours * 1800  # 1000 messages per hour
        expected_drops = total_messages // droptime
        
        print(f"Expected total messages: {total_messages}")
        print(f"Expected number of drops: {expected_drops}")
        
        # Get drop settings
        settings = await self.db.get_drop_settings()
        rarity_weights = settings.get('rarity_weights', {})
        daily_limits = settings.get('daily_limits', {})
        
        # Calculate total weight
        total_weight = sum(rarity_weights.values())
        
        # Calculate expected distribution
        distribution = {}
        for rarity, weight in rarity_weights.items():
            if weight > 0:  # Only include rarities that can drop
                expected_count = (weight / total_weight) * expected_drops
                daily_limit = daily_limits.get(rarity)
                
                # Apply daily limit if it exists
                if daily_limit is not None:
                    expected_count = min(expected_count, daily_limit * (duration_hours / 24))
                
                distribution[rarity] = {
                    "expected_count": round(expected_count, 2),
                    "percentage": round((expected_count / expected_drops) * 100, 2)
                }
        
        # Print results
        print("\n=== Expected Drop Distribution ===")
        print(f"Total Expected Drops: {expected_drops}")
        print("\nRarity Distribution:")
        for rarity, data in sorted(distribution.items(), key=lambda x: x[1]["expected_count"], reverse=True):
            print(f"{rarity}: {data['expected_count']} drops ({data['percentage']}%)")
        
        # Save results
        results = {
            "total_messages": total_messages,
            "expected_drops": expected_drops,
            "distribution": distribution,
            "settings": {
                "rarity_weights": rarity_weights,
                "daily_limits": daily_limits
            }
        }
        
        filename = f"drop_distribution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {filename}")
        
        return results

async def main():
    simulator = DropSimulator()
    await simulator.calculate_expected_distribution(duration_hours=24, droptime=20)

if __name__ == "__main__":
    asyncio.run(main()) 