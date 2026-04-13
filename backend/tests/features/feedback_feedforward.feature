Feature: Feedback and Feedforward
  As a DevLog+ user
  I want to give feedback on generated content and steer future generation
  So the system adapts to my preferences

  Scenario: Submit thumbs-up feedback on a quiz question
    Given a quiz session exists with questions
    When I submit thumbs-up feedback for the first question
    Then the feedback should be recorded with reaction "thumbs_up"

  Scenario: Submit feedforward note on a project
    Given a project exists
    When I submit feedback with note "More focus on error handling patterns" for the project
    Then the feedback should be recorded with the feedforward note

  Scenario: Feedback is available for pipeline context
    Given I have submitted feedback with note "harder debugging tasks"
    When I list all feedback
    Then the feedforward note "harder debugging tasks" should be present
