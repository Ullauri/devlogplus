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

  Scenario: A previously thumbs-upped recommendation is not re-recommended
    Given the reading allowlist contains "go.dev" and "blog.golang.org"
    And I have thumbs-upped a previous reading at "https://go.dev/doc/effective_go#concurrency"
    When the reading generation pipeline runs and proposes that same URL again
    Then the previously-liked URL should not appear in the new batch
    And the processing log should record one skipped already-liked recommendation

  Scenario: A previously recommended URL is not re-recommended even if the title differs
    Given the reading allowlist contains "go.dev" and "blog.golang.org"
    And a reading at "https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/" already exists in the database
    When the reading generation pipeline runs and proposes that same URL with a different title
    Then the duplicate URL should not appear in the new batch
    And the processing log should record one skipped duplicate-url recommendation

  Scenario: Multiple recommendations on the same topic are deduplicated for diversity
    Given the reading allowlist contains "go.dev" and "blog.golang.org"
    When the reading generation pipeline runs with two recommendations targeting the same topic
    Then only one recommendation should be stored for that topic
    And the processing log should record one skipped duplicate-topic recommendation
