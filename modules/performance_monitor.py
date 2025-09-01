"""
Performance Monitoring and Optimization Module
Tracks bot performance and automatically optimizes when issues are detected
"""

import asyncio
import time
import psutil
import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional
import gc
import threading
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class PerformanceLevel(Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class PerformanceMetrics:
    timestamp: float
    memory_percent: float
    cpu_percent: float
    active_connections: int
    cache_hit_rate: float
    query_response_time: float
    error_rate: float

class PerformanceMonitor:
    def __init__(self):
        self.metrics_history = deque(maxlen=100)
        self.alerts = deque(maxlen=50)
        self.optimization_history = deque(maxlen=20)
        self.is_monitoring = False
        self.monitor_task = None
        self.optimization_task = None
        
        # Performance thresholds
        self.thresholds = {
            'memory_warning': 75.0,
            'memory_critical': 90.0,
            'cpu_warning': 80.0,
            'cpu_critical': 95.0,
            'response_time_warning': 2.0,  # seconds
            'response_time_critical': 5.0,
            'error_rate_warning': 0.05,  # 5%
            'error_rate_critical': 0.15   # 15%
        }
        
        # Optimization strategies
        self.optimization_strategies = {
            'memory_high': self._optimize_memory,
            'cpu_high': self._optimize_cpu,
            'response_slow': self._optimize_response_time,
            'error_high': self._optimize_error_rate
        }
    
    async def start_monitoring(self):
        """Start performance monitoring"""
        if self.is_monitoring:
            return
            
        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        self.optimization_task = asyncio.create_task(self._optimization_loop())
        logger.info("Performance monitoring started")
    
    async def stop_monitoring(self):
        """Stop performance monitoring"""
        self.is_monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
        if self.optimization_task:
            self.optimization_task.cancel()
        logger.info("Performance monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                metrics = await self._collect_metrics()
                self.metrics_history.append(metrics)
                
                # Check for performance issues
                issues = self._detect_issues(metrics)
                if issues:
                    await self._handle_issues(issues)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def _collect_metrics(self) -> PerformanceMetrics:
        """Collect current performance metrics"""
        try:
            # Memory metrics
            memory = psutil.virtual_memory()
            
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Database connection metrics (simplified)
            active_connections = 0  # This would be fetched from your DB client
            
            # Cache metrics (simplified)
            cache_hit_rate = 0.8  # This would be calculated from your cache stats
            
            # Query response time (simplified)
            query_response_time = 0.1  # This would be measured from actual queries
            
            # Error rate (simplified)
            error_rate = 0.01  # This would be calculated from actual errors
            
            return PerformanceMetrics(
                timestamp=time.time(),
                memory_percent=memory.percent,
                cpu_percent=cpu_percent,
                active_connections=active_connections,
                cache_hit_rate=cache_hit_rate,
                query_response_time=query_response_time,
                error_rate=error_rate
            )
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            return PerformanceMetrics(
                timestamp=time.time(),
                memory_percent=0.0,
                cpu_percent=0.0,
                active_connections=0,
                cache_hit_rate=0.0,
                query_response_time=0.0,
                error_rate=0.0
            )
    
    def _detect_issues(self, metrics: PerformanceMetrics) -> List[str]:
        """Detect performance issues based on metrics"""
        issues = []
        
        # Memory issues
        if metrics.memory_percent > self.thresholds['memory_critical']:
            issues.append('memory_critical')
        elif metrics.memory_percent > self.thresholds['memory_warning']:
            issues.append('memory_high')
        
        # CPU issues
        if metrics.cpu_percent > self.thresholds['cpu_critical']:
            issues.append('cpu_critical')
        elif metrics.cpu_percent > self.thresholds['cpu_warning']:
            issues.append('cpu_high')
        
        # Response time issues
        if metrics.query_response_time > self.thresholds['response_time_critical']:
            issues.append('response_critical')
        elif metrics.query_response_time > self.thresholds['response_time_warning']:
            issues.append('response_slow')
        
        # Error rate issues
        if metrics.error_rate > self.thresholds['error_rate_critical']:
            issues.append('error_critical')
        elif metrics.error_rate > self.thresholds['error_rate_warning']:
            issues.append('error_high')
        
        return issues
    
    async def _handle_issues(self, issues: List[str]):
        """Handle detected performance issues"""
        for issue in issues:
            try:
                if issue in self.optimization_strategies:
                    await self.optimization_strategies[issue]()
                
                # Log alert
                alert = {
                    'timestamp': datetime.now(),
                    'issue': issue,
                    'severity': 'critical' if 'critical' in issue else 'warning'
                }
                self.alerts.append(alert)
                logger.warning(f"Performance issue detected: {issue}")
                
            except Exception as e:
                logger.error(f"Error handling issue {issue}: {e}")
    
    async def _optimize_memory(self):
        """Optimize memory usage"""
        try:
            # Force garbage collection
            collected = gc.collect()
            logger.info(f"Memory optimization: collected {collected} objects")
            
            # Clear caches if available
            import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
else:
    from .database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
            clear_all_caches()
            
            # Log optimization
            self.optimization_history.append({
                'timestamp': datetime.now(),
                'type': 'memory_optimization',
                'details': f'Collected {collected} objects, cleared caches'
            })
            
        except Exception as e:
            logger.error(f"Error in memory optimization: {e}")
    
    async def _optimize_cpu(self):
        """Optimize CPU usage"""
        try:
            # Reduce cache sizes temporarily
            import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
else:
    from .database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
            if len(_character_cache) > 500:
                # Clear half of the cache
                keys_to_remove = list(_character_cache.keys())[:len(_character_cache)//2]
                for key in keys_to_remove:
                    del _character_cache[key]
            
            # Log optimization
            self.optimization_history.append({
                'timestamp': datetime.now(),
                'type': 'cpu_optimization',
                'details': 'Reduced cache sizes'
            })
            
        except Exception as e:
            logger.error(f"Error in CPU optimization: {e}")
    
    async def _optimize_response_time(self):
        """Optimize response time"""
        try:
            # Clear all caches to force fresh data
            import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
else:
    from .database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
            clear_all_caches()
            
            # Log optimization
            self.optimization_history.append({
                'timestamp': datetime.now(),
                'type': 'response_time_optimization',
                'details': 'Cleared all caches for fresh data'
            })
            
        except Exception as e:
            logger.error(f"Error in response time optimization: {e}")
    
    async def _optimize_error_rate(self):
        """Optimize error rate"""
        try:
            # Reset connection pool if needed
            import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
else:
    from .database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
            pass  # MongoDB logic removed
            
            # Log optimization
            self.optimization_history.append({
                'timestamp': datetime.now(),
                'type': 'error_rate_optimization',
                'details': 'Reset database connection'
            })
            
        except Exception as e:
            logger.error(f"Error in error rate optimization: {e}")
    
    async def _optimization_loop(self):
        """Background optimization loop"""
        while self.is_monitoring:
            try:
                # Check if we need periodic optimization
                if len(self.metrics_history) > 10:
                    recent_metrics = list(self.metrics_history)[-10:]
                    avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
                    avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
                    
                    # If consistently high, apply optimizations
                    if avg_memory > 70 or avg_cpu > 70:
                        await self._optimize_memory()
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in optimization loop: {e}")
                await asyncio.sleep(60)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of current performance"""
        if not self.metrics_history:
            return {"status": "No metrics available"}
        
        latest_metrics = self.metrics_history[-1]
        recent_metrics = list(self.metrics_history)[-10:] if len(self.metrics_history) >= 10 else list(self.metrics_history)
        
        # Calculate averages
        avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
        avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
        avg_response_time = sum(m.query_response_time for m in recent_metrics) / len(recent_metrics)
        
        # Determine performance level
        if avg_memory < 50 and avg_cpu < 50 and avg_response_time < 1.0:
            performance_level = PerformanceLevel.EXCELLENT
        elif avg_memory < 70 and avg_cpu < 70 and avg_response_time < 2.0:
            performance_level = PerformanceLevel.GOOD
        elif avg_memory < 85 and avg_cpu < 85 and avg_response_time < 3.0:
            performance_level = PerformanceLevel.WARNING
        else:
            performance_level = PerformanceLevel.CRITICAL
        
        return {
            "current_metrics": {
                "memory_percent": latest_metrics.memory_percent,
                "cpu_percent": latest_metrics.cpu_percent,
                "cache_hit_rate": latest_metrics.cache_hit_rate,
                "query_response_time": latest_metrics.query_response_time,
                "error_rate": latest_metrics.error_rate
            },
            "average_metrics": {
                "memory_percent": avg_memory,
                "cpu_percent": avg_cpu,
                "response_time": avg_response_time
            },
            "performance_level": performance_level.value,
            "recent_alerts": len([a for a in self.alerts if (datetime.now() - a['timestamp']).seconds < 3600]),
            "optimizations_applied": len(self.optimization_history),
            "monitoring_duration": len(self.metrics_history) * 30  # seconds
        }

# Global performance monitor instance
performance_monitor = PerformanceMonitor()

async def start_performance_monitoring():
    """Start the performance monitoring system"""
    await performance_monitor.start_monitoring()

async def stop_performance_monitoring():
    """Stop the performance monitoring system"""
    await performance_monitor.stop_monitoring()

def get_performance_summary():
    """Get current performance summary"""
    return performance_monitor.get_performance_summary() 