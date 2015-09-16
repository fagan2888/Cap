EXECUTE_PROCESS(
    COMMAND ${GIT_EXECUTABLE} rev-parse HEAD
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE GIT_COMMIT_HASH
    OUTPUT_STRIP_TRAILING_WHITESPACE
    )
EXECUTE_PROCESS(
    COMMAND ${GIT_EXECUTABLE} rev-parse --abbrev-ref HEAD
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE GIT_BRANCH
    OUTPUT_STRIP_TRAILING_WHITESPACE
    )
EXECUTE_PROCESS(
    COMMAND ${GIT_EXECUTABLE} rev-parse --symbolic-full-name HEAD
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE GIT_HEAD_REF
    OUTPUT_STRIP_TRAILING_WHITESPACE
    )
EXECUTE_PROCESS(
    COMMAND cat .git/${GIT_HEAD_REF}
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE DUMMY
    OUTPUT_STRIP_TRAILING_WHITESPACE
    )
MESSAGE("GIT_HEAD_REF=${GIT_HEAD_REF}")
MESSAGE("GIT_COMMIT_HASH=${GIT_COMMIT_HASH}")
MESSAGE("GIT_BRANCH=${GIT_BRANCH}")
CONFIGURE_FILE(${CMAKE_SOURCE_DIR}/cmake/version.h.in ${CMAKE_BINARY_DIR}/include/cap/version.h)
