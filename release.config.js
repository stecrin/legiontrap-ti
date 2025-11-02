export default {
    branches: ["main"],
    repositoryUrl: "https://github.com/stecrin/legiontrap-ti",
    plugins: [
      "@semantic-release/commit-analyzer",
      "@semantic-release/release-notes-generator",
      [
        "@semantic-release/changelog",
        {
          changelogFile: "CHANGELOG.md",
          changelogTitle: "# Changelog\n\nAll notable changes to this project will be documented in this file.\n",
        },
      ],
      [
        "@semantic-release/git",
        {
          assets: ["CHANGELOG.md"],
          message: "🔖 Release ${nextRelease.version}\n\n${nextRelease.notes}",
        },
      ],
      "@semantic-release/github",
    ],
  };
