Feature: Nightly Profile Update Pipeline
  As the DevLog+ system
  I want to process new journal entries and extract topics via LLM
  So the Knowledge Profile stays current with the user's learning

  Background:
    Given onboarding has been completed

  Scenario: Process journal entries and update profile
    Given I have an unprocessed journal entry with content "Today I studied Go concurrency patterns including goroutines, channels, and the select statement. I also explored mutex usage for shared state."
    When the nightly profile update pipeline runs
    Then the pipeline should complete successfully
    And new topics should appear in the Knowledge Profile
    And the journal entry should be marked as processed
    And a profile snapshot should be created

  Scenario: No new entries skips the update
    When the nightly profile update pipeline runs
    Then the pipeline should report no new entries

  Scenario: Blocking triage prevents profile update
    Given there is a critical unresolved triage item
    When the nightly profile update pipeline runs
    Then the pipeline should be blocked by triage
