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

  Scenario: Project title collision with a previously-reacted project is logged
    Given a previously issued project titled "Concurrent File Processor" has been thumbs-upped
    When the project generation pipeline runs and proposes that same title
    Then the project should still be created
    And the processing log should flag the project title collision

  Scenario: Duplicate task titles within a generated project are deduplicated
    When the project generation pipeline runs with two tasks sharing the same title
    Then only one task with that title should be stored
    And the processing log should record one skipped duplicate task

  Scenario: A thumbs-upped past task title is not re-issued in a new project
    Given a previously issued project with a thumbs-upped task titled "Fix race condition"
    When the project generation pipeline runs and proposes that same task title
    Then the previously-liked task title should not appear in the new project
    And the processing log should record one skipped reacted-to task
