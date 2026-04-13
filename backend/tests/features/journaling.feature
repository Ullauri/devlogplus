Feature: Journal Entry Lifecycle
  As a developer using DevLog+
  I want to create and manage journal entries about my learning
  So that the system can build my Knowledge Profile over time

  Scenario: Create a new journal entry
    When I create a journal entry titled "Go Goroutines" with content "Learned about goroutines and channels today"
    Then the entry should be created successfully
    And the entry should have title "Go Goroutines"
    And the entry should not be processed yet

  Scenario: Edit a journal entry creates a new version
    Given I have a journal entry titled "Draft Notes" with content "Initial content"
    When I edit the entry with title "Revised Notes" and content "Updated and improved content"
    Then the entry title should be "Revised Notes"
    And the entry current content should be "Updated and improved content"
    And the entry should have 2 versions

  Scenario: List journal entries shows most recent first
    Given I have a journal entry titled "First Entry" with content "Content A"
    And I have a journal entry titled "Second Entry" with content "Content B"
    When I list all journal entries
    Then I should see 2 entries in the list

  Scenario: Delete a journal entry removes it and its versions
    Given I have a journal entry titled "Temporary" with content "Will be deleted"
    When I delete the entry
    Then the entry should no longer exist
