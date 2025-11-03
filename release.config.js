export default {
    branches: ["main"],
    repositoryUrl: "https://github.com/stecrin/legiontrap-ti",
    plugins: [
      [
        "@semantic-release/commit-analyzer",
        {
          preset: "conventionalcommits",
        },
      ],
      [
        "@semantic-release/release-notes-generator",
        {
          preset: "conventionalcommits",
        },
      ],
      [
        "@semantic-release/changelog",
        {
          changelogFile: "CHANGELOG.md",
          changelogTitle:
            "# Changelog\n\nAll notable changes to this project will be documented in this file.\n",
        },
      ],
      [
        "@semantic-release/git",
        {
          assets: ["CHANGELOG.md"],
          message: "🔖 chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}",
        },
      ],
      [
        "@semantic-release/github",
        {
          assets: [{ path: "CHANGELOG.md", label: "Changelog" }],
        },
      ],
    ],
  };
