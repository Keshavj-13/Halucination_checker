import json
import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("audit-api.data-collector")

class DataCollector:
    """
    Saves audit results to a JSONL file for future ML training.
    """
    def __init__(self, filepath: str = None):
        if filepath is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            filepath = os.path.join(backend_dir, "data", "training_data.jsonl")

        self.filepath = filepath
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

    def collect(self, claim: str, evidence: list, results: Dict[str, Any]):
        """
        Appends a new record to the training data file.
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "claim": claim,
            "evidence": [ev.model_dump() for ev in evidence],
            "layer_results": results
        }
        
        try:
            with open(self.filepath, "a") as f:
                f.write(json.dumps(record) + "\n")
            logger.info(f"Collected data for claim: {claim[:30]}...")
        except Exception as e:
            logger.error(f"Failed to collect data: {str(e)}")

data_collector = DataCollector()
