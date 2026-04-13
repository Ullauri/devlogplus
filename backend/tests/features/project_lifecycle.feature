Feature: Weekly Project Generation, Submission, and Evaluation
  As a DevLog+ user
  I want to receive weekly Go micro-projects and get feedback on submissions
  So I can practice and improve my Go programming skills

  Background:
    Given onboarding has been completed with go experience "beginner"
    And the Knowledge Profile has topics

  Scenario: Generate a new weekly project
    When the project generation pipeline runs
    Then a new project should be created with status "issued"
    And the project should have tasks
    And the project files should be written to disk

  Scenario: Submit a project for evaluation
    Given a project exists with status "issued"
    When I submit the project with notes "Completed all tasks"
    Then the project status should be "submitted"

  Scenario: Evaluate a submitted project
    Given a submitted project exists with code on disk
    When the project evaluation pipeline runs
    Then the project should have an evaluation
    And the project status should be "evaluated"
    And the evaluation should include a code quality score
