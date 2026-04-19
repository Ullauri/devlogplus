Feature: Weekly Reading Recommendations
  As a DevLog+ user
  I want to receive curated reading recommendations from trusted sources
  So I can deepen my knowledge in relevant areas

  Background:
    Given onboarding has been completed
    And the Knowledge Profile has topics

  Scenario: Generate reading recommendations
    Given the reading allowlist contains "go.dev" and "blog.golang.org"
    When the reading generation pipeline runs
    Then reading recommendations should be created
    And all recommendations should be from allowlisted domains

  Scenario: Recommendations from non-allowlisted domains are filtered out
    Given the reading allowlist contains only "go.dev"
    When the reading generation pipeline runs with a response containing a non-allowlisted domain
    Then only recommendations from "go.dev" should be stored

  Scenario: Recommendations with unreachable URLs are filtered out
    Given the reading allowlist contains "go.dev" and "blog.golang.org"
    When the reading generation pipeline runs and one URL returns 404
    Then only recommendations with reachable URLs should be stored
    And the processing log should record the skipped URL
