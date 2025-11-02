export default {
    branches: ["main"],
    repositoryUrl: "https://github.com/stecrin/legiontrap-ti",
    plugins: [
      [
        "@semantic-release/commit-analyzer",
        {
          preset: "angular",
        },
      ],
      "@semantic-release/release-notes-generator",
      [
        "@semantic-release/changelog",
        {
          changelogFile: "CHANGELOG.md",
        },
      ],
      [
        "@semantic-release/git",
        {
          assets: ["CHANGELOG.md", "README.md"],
          message: "🔖 chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}",
        },
      ],
      "@semantic-release/github",
    ],
  };
