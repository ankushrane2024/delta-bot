import unittest
import os
import re

class TestSecretLeakAudit(unittest.TestCase):
    """
    Mandatory Acceptance Test:
    Scans all logs to verify ZERO secrets (API Key, API Secret, Authorization Header)
    have been leaked.
    """
    def test_no_secrets_in_logs(self):
        log_dir = "logs"
        if not os.path.exists(log_dir):
            return # Nothing to scan
            
        log_files = [
            "startup.log", "system.log", "provider.log", 
            "execution.log", "dashboard.log", "audit.log", "recovery.log"
        ]
        
        # Regexes for common secret exposures that might bypass the SecretRedactingFormatter
        forbidden_patterns = [
            re.compile(r'"api-key"\s*:\s*"[^*]+"', re.IGNORECASE),
            re.compile(r'"Authorization"\s*:\s*".*Bearer\s+[^*]+"', re.IGNORECASE),
            re.compile(r'"DELTA_API_SECRET"\s*:\s*"[^*]+"', re.IGNORECASE),
        ]
        
        for lf in log_files:
            file_path = os.path.join(log_dir, lf)
            if not os.path.exists(file_path):
                continue
                
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            for pattern in forbidden_patterns:
                matches = pattern.findall(content)
                self.assertEqual(
                    len(matches), 0, 
                    f"Secret leak detected in {lf}! Pattern matched: {pattern.pattern}"
                )

if __name__ == '__main__':
    unittest.main()
