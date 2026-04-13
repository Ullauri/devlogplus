Feature: Triage Item Resolution
  As a DevLog+ user
  I want to resolve triage items that the system can't confidently handle
  So the system can continue processing without errors

  Scenario: Resolve a triage item with clarification
    Given there is a pending triage item with severity "medium"
    When I resolve the triage item with action "accepted" and text "This is correct"
    Then the triage item should have status "accepted"
    And the triage item should have resolution text "This is correct"

  Scenario: Critical triage blocks the pipeline until resolved
    Given there is a critical unresolved triage item
    When I check for blocking triage items
    Then the system should report blocking triage
    When I resolve the critical triage item with action "edited" and text "Corrected the topic"
    And I check for blocking triage items
    Then the system should report no blocking triage

  Scenario: Filter triage items by severity
    Given there is a pending triage item with severity "low"
    And there is a pending triage item with severity "critical"
    When I list triage items filtered by severity "critical"
    Then I should see only critical triage items
