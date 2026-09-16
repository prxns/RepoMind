import unittest

from repomind.source import chunk_text, fingerprint, normalized_text, parse_repo_url, supported_file


class SourceTests(unittest.TestCase):
    def test_repo_urls_are_restricted(self):
        self.assertEqual(parse_repo_url("https://github.com/example/project.git"), ("example", "project"))
        for url in ("http://github.com/a/b", "https://evil.example/a/b", "https://github.com/a/b/tree/main",
                    "https://github.com/a/b?x=1", "https://github.com@evil.example/a/b"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_repo_url(url)

    def test_filter_and_binary(self):
        self.assertEqual(supported_file("src/service.py", 100, 1000), "Python")
        for path in ("node_modules/a.py", "dist/app.js", "image.png", "package-lock.json", "../secrets.txt"):
            with self.subTest(path=path):
                self.assertIsNone(supported_file(path, 10, 1000))
        self.assertIsNone(normalized_text(b"text\x00data"))
        self.assertEqual(normalized_text(b"a\r\nb"), "a\nb")

    def test_markdown_chunks_preserve_heading_boundaries_and_lines(self):
        text = "# Intro\none\ntwo\n## Next\nthree\nfour"
        parts = chunk_text("README.md", text, "Markdown", target=3, overlap=1)
        self.assertEqual([(p.start_line, p.end_line) for p in parts], [(1, 3), (4, 6)])
        self.assertEqual(parts[0].content, "# Intro\none\ntwo")
        self.assertEqual(parts[0].content_hash, chunk_text("README.md", text, "Markdown", 3, 1)[0].content_hash)

    def test_line_window_overlap_and_fingerprint(self):
        text = "\n".join(str(i) for i in range(1, 8))
        parts = chunk_text("a.py", text, "Python", target=4, overlap=1)
        self.assertEqual([(p.start_line, p.end_line) for p in parts], [(1, 4), (4, 7)])
        self.assertNotEqual(fingerprint("a", "bc"), fingerprint("ab", "c"))


if __name__ == "__main__":
    unittest.main()
