"""
Multi-tier Cache Manager
========================
Three levels of caching with configurable TTL:

  L1 — In-memory LRU dict   (fastest, lost on restart)
  L2 — On-disk JSON files    (survives restarts, 24h default TTL)
  L3 — Stale fallback        (serves expired data if API is down)

Features:
  • Per-key TTL override
  • Cache warming on startup
  • Stats tracking (hits/misses per tier)
  • Thread-safe with locks
"""

import os
import json
import time
import hashlib
import threading
from collections import OrderedDict


class CacheManager:
    def __init__(self, cache_dir=".cache", memory_max_items=500, default_ttl=86400):
        self.cache_dir = cache_dir
        self.memory_max_items = memory_max_items
        self.default_ttl = default_ttl  # 24 hours

        # L1: In-memory LRU
        self._memory = OrderedDict()
        self._lock = threading.Lock()

        # Stats
        self._stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_stale_hits": 0,
            "misses": 0,
            "writes": 0,
        }

        # Ensure cache directories exist
        os.makedirs(os.path.join(cache_dir, "l2"), exist_ok=True)
        os.makedirs(os.path.join(cache_dir, "l3_stale"), exist_ok=True)

    def _make_key(self, namespace, params):
        """Create a deterministic cache key from namespace + params."""
        raw = f"{namespace}:{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _disk_path(self, key, tier="l2"):
        return os.path.join(self.cache_dir, tier, f"{key}.json")

    def get(self, namespace, params, ttl=None):
        """
        Try to retrieve from cache. Returns (data, cache_tier) or (None, None).
        """
        ttl = ttl or self.default_ttl
        key = self._make_key(namespace, params)
        now = time.time()

        # L1: Memory
        with self._lock:
            if key in self._memory:
                entry = self._memory[key]
                if now - entry["ts"] < ttl:
                    self._memory.move_to_end(key)
                    self._stats["l1_hits"] += 1
                    return entry["data"], "L1_MEMORY"

        # L2: Disk (fresh)
        disk_path = self._disk_path(key, "l2")
        if os.path.exists(disk_path):
            try:
                with open(disk_path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                if now - entry["ts"] < ttl:
                    # Promote to L1
                    self._promote_to_memory(key, entry)
                    self._stats["l2_hits"] += 1
                    return entry["data"], "L2_DISK"
            except (json.JSONDecodeError, KeyError):
                pass

        # L3: Stale fallback (expired but usable if API fails)
        stale_path = self._disk_path(key, "l3_stale")
        if os.path.exists(stale_path):
            try:
                with open(stale_path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                self._stats["l3_stale_hits"] += 1
                return entry["data"], "L3_STALE"
            except (json.JSONDecodeError, KeyError):
                pass

        self._stats["misses"] += 1
        return None, None

    def get_fresh(self, namespace, params, ttl=None):
        """
        Get from cache only if fresh (L1 or L2 within TTL).
        Does NOT fall back to stale.
        """
        ttl = ttl or self.default_ttl
        key = self._make_key(namespace, params)
        now = time.time()

        with self._lock:
            if key in self._memory:
                entry = self._memory[key]
                if now - entry["ts"] < ttl:
                    self._memory.move_to_end(key)
                    self._stats["l1_hits"] += 1
                    return entry["data"], "L1_MEMORY"

        disk_path = self._disk_path(key, "l2")
        if os.path.exists(disk_path):
            try:
                with open(disk_path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                if now - entry["ts"] < ttl:
                    self._promote_to_memory(key, entry)
                    self._stats["l2_hits"] += 1
                    return entry["data"], "L2_DISK"
            except (json.JSONDecodeError, KeyError):
                pass

        self._stats["misses"] += 1
        return None, None

    def set(self, namespace, params, data, ttl=None):
        """Write data to all cache tiers."""
        key = self._make_key(namespace, params)
        entry = {"data": data, "ts": time.time(), "ttl": ttl or self.default_ttl}

        # L1: Memory
        with self._lock:
            self._memory[key] = entry
            self._memory.move_to_end(key)
            # Evict LRU if over capacity
            while len(self._memory) > self.memory_max_items:
                self._memory.popitem(last=False)

        # L2: Disk (fresh)
        try:
            with open(self._disk_path(key, "l2"), "w", encoding="utf-8") as f:
                json.dump(entry, f)
        except OSError:
            pass

        # L3: Stale backup (always write, never auto-expire)
        try:
            with open(self._disk_path(key, "l3_stale"), "w", encoding="utf-8") as f:
                json.dump(entry, f)
        except OSError:
            pass

        self._stats["writes"] += 1

    def invalidate(self, namespace, params):
        """Remove a specific key from all tiers."""
        key = self._make_key(namespace, params)
        with self._lock:
            self._memory.pop(key, None)
        for tier in ("l2", "l3_stale"):
            path = self._disk_path(key, tier)
            if os.path.exists(path):
                os.remove(path)

    def clear(self, tier="all"):
        """Clear cache. tier can be 'l1', 'l2', 'l3', or 'all'."""
        if tier in ("l1", "all"):
            with self._lock:
                self._memory.clear()
        if tier in ("l2", "all"):
            self._clear_dir(os.path.join(self.cache_dir, "l2"))
        if tier in ("l3", "all"):
            self._clear_dir(os.path.join(self.cache_dir, "l3_stale"))

    def _clear_dir(self, dirpath):
        if os.path.exists(dirpath):
            for f in os.listdir(dirpath):
                fp = os.path.join(dirpath, f)
                if os.path.isfile(fp):
                    os.remove(fp)

    def _promote_to_memory(self, key, entry):
        with self._lock:
            self._memory[key] = entry
            self._memory.move_to_end(key)
            while len(self._memory) > self.memory_max_items:
                self._memory.popitem(last=False)

    def stats(self):
        with self._lock:
            mem_count = len(self._memory)
        l2_dir = os.path.join(self.cache_dir, "l2")
        l2_count = len(os.listdir(l2_dir)) if os.path.exists(l2_dir) else 0
        return {
            **self._stats,
            "l1_items": mem_count,
            "l2_items": l2_count,
            "memory_max": self.memory_max_items,
            "default_ttl_hours": round(self.default_ttl / 3600, 1),
        }

    def warm(self, namespace_params_list):
        """
        Pre-load entries from L2 disk into L1 memory.
        Accepts list of (namespace, params) tuples.
        """
        loaded = 0
        for namespace, params in namespace_params_list:
            key = self._make_key(namespace, params)
            disk_path = self._disk_path(key, "l2")
            if os.path.exists(disk_path):
                try:
                    with open(disk_path, "r", encoding="utf-8") as f:
                        entry = json.load(f)
                    self._promote_to_memory(key, entry)
                    loaded += 1
                except (json.JSONDecodeError, KeyError):
                    pass
        return loaded
