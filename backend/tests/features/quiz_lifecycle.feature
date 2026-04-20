Feature: Quiz Generation, Answering, and Evaluation
  As a DevLog+ user
  I want to take weekly quizzes calibrated to my knowledge
  So I can reinforce learning and discover gaps

  Background:
    Given onboarding has been completed
    And the Knowledge Profile has topics

  Scenario: Generate a weekly quiz
    When the quiz generation pipeline runs
    Then a new quiz session should be created with status "pending"
    And the quiz should have questions

  Scenario: Answer quiz questions and complete session
    Given a quiz session exists with questions
    When I submit an answer "Goroutines are lightweight threads managed by the Go runtime" for the first question
    Then the answer should be recorded
    And the quiz session status should be "in_progress"
    When I complete the quiz session
    Then the quiz session status should be "completed"

  Scenario: Evaluate a completed quiz
    Given a completed quiz session with answers exists
    When the quiz evaluation pipeline runs
    Then each question should have an evaluation
    And the quiz session status should be "evaluated"

  Scenario: A previously thumbs-upped quiz question is not re-asked
    Given a previously asked question "Explain goroutines." has been thumbs-upped
    When the quiz generation pipeline runs and proposes that same question again
    Then the previously-liked question should not appear in the new session
    And the processing log should record one skipped already-liked question

  Scenario: Multiple quiz questions on the same topic are deduplicated for diversity
    When the quiz generation pipeline runs with two questions targeting the same topic
    Then only one question should be stored for that topic
    And the session question_count should match the number of stored questions
    And the processing log should record one skipped duplicate-topic question
