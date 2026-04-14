Feature: Data Transfer (Export / Import)
  As a developer using DevLog+
  I want to export all my data and import it on another machine
  So that I can move my learning progress between devices

  Scenario: Export an empty database
    When I export all data
    Then the export should succeed
    And the export bundle should have format version 1
    And the export bundle should contain 0 journal entries

  Scenario: Export a populated database
    Given I have a journal entry titled "Go Interfaces" with content "Learned about implicit interfaces"
    And I have topics in my knowledge profile
    When I export all data
    Then the export should succeed
    And the export bundle should contain 1 journal entries
    And the export bundle should contain 2 topics

  Scenario: Preview export metadata before downloading
    Given I have a journal entry titled "Go Testing" with content "Table-driven tests are great"
    When I request export metadata
    Then the metadata should show 1 journal entries
    And the metadata should show 1 journal entry versions

  Scenario: Round-trip export and import
    Given I have a journal entry titled "Concurrency" with content "Goroutines and channels"
    And I have topics in my knowledge profile
    When I export all data
    And I import the exported bundle with overwrite confirmed
    Then the import should succeed
    And the imported data should contain 1 journal entries
    And the journal entry titled "Concurrency" should still exist

  Scenario: Import into an empty database without confirmation
    Given I have an export bundle with 1 journal entry
    When I import the bundle into an empty database
    Then the import should succeed

  Scenario: Import into a populated database is blocked without confirmation
    Given I have a journal entry titled "Existing" with content "Should not be lost"
    And I have an export bundle with 1 journal entry
    When I import the bundle without confirming overwrite
    Then the import should be rejected with a conflict error
    And the original journal entry "Existing" should still exist

  Scenario: Import into a populated database succeeds with confirmation
    Given I have a journal entry titled "Old Data" with content "Will be replaced"
    And I have an export bundle with 1 journal entry
    When I import the bundle with overwrite confirmed
    Then the import should succeed
    And the original journal entry "Old Data" should no longer exist

  Scenario: Import replaces data rather than merging
    Given I have a journal entry titled "Original" with content "First machine"
    And I have an export bundle containing a journal entry titled "Replacement"
    When I import the bundle with overwrite confirmed
    Then the import should succeed
    And the journal entry titled "Replacement" should still exist
    And the original journal entry "Original" should no longer exist

  Scenario: Import rejects invalid file
    When I import an invalid JSON file
    Then the import should be rejected with a validation error

  Scenario: Import rejects unsupported format version
    When I import a bundle with format version 999
    Then the import should be rejected with a validation error about format version
