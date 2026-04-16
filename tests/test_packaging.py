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

    def test_personal_kubernetes_manifest_targets_public_dockerhub_image(self):
        manifest_path = ROOT / "deploy" / "kubernetes-personal.yaml"
        manifest = manifest_path.read_text()

        self.assertTrue(manifest_path.exists())
        self.assertIn("DEEPWORK_PERSONAL_MODE: \"1\"", manifest)
        self.assertIn("DEEPWORK_DB_BACKEND: sqlite", manifest)
        self.assertIn("image: yavarkhodadadi/deep-work-4dx:latest", manifest)
        self.assertIn("mountPath: /data", manifest)

    def test_readme_documents_personal_kubernetes_apply_path(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn("kubectl apply -f deploy/kubernetes-personal.yaml", readme)
        self.assertIn("yavarkhodadadi/deep-work-4dx:latest", readme)
        self.assertIn("DEEPWORK_PERSONAL_MODE", readme)

    def test_github_actions_workflow_publishes_docker_image(self):
        workflow_path = ROOT / ".github" / "workflows" / "docker-publish.yml"
        workflow = workflow_path.read_text()

        self.assertTrue(workflow_path.exists())
        self.assertIn("docker/setup-qemu-action", workflow)
        self.assertIn("docker/login-action", workflow)
        self.assertIn("docker/build-push-action", workflow)
        self.assertIn("platforms: linux/amd64,linux/arm64", workflow)
        self.assertIn("yavarkhodadadi/deep-work-4dx", workflow)

    def test_personal_kubernetes_smoke_script_exists(self):
        smoke_script_path = ROOT / "scripts" / "k8s_personal_smoke.sh"
        smoke_script = smoke_script_path.read_text()

        self.assertTrue(smoke_script_path.exists())
        self.assertIn("kind", smoke_script)
        self.assertIn("MANIFEST_PATH", smoke_script)
        self.assertIn("kubernetes-personal.yaml", smoke_script)
        self.assertIn("deepwork-personal", smoke_script)


if __name__ == "__main__":
    unittest.main()
