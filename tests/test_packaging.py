import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class PackagingTests(unittest.TestCase):
    def test_requirements_include_postgres_driver(self):
        requirements = (ROOT / "requirements.txt").read_text()

        self.assertIn("psycopg", requirements)

    def test_dockerfile_does_not_embed_secret_key_env(self):
        dockerfile = (ROOT / "Dockerfile").read_text()

        self.assertNotIn("ENV DEEPWORK_SECRET_KEY", dockerfile)
        self.assertIn("ENV DEEPWORK_DB_PATH=/data/deepwork.db", dockerfile)

    def test_kubernetes_manifest_is_present_as_single_file(self):
        manifest_path = ROOT / "deploy" / "kubernetes.yaml"
        manifest = manifest_path.read_text()

        self.assertTrue(manifest_path.exists())
        self.assertIn("kind: Secret", manifest)
        self.assertIn("kind: ConfigMap", manifest)
        self.assertIn("kind: PersistentVolumeClaim", manifest)
        self.assertIn("kind: Deployment", manifest)
        self.assertIn("kind: Service", manifest)
        self.assertIn("DEEPWORK_SECRET_KEY", manifest)
        self.assertIn("mountPath: /data", manifest)


if __name__ == "__main__":
    unittest.main()
