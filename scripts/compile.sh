#!/bin/bash

set -euo pipefail

source "${INTERNALS}/util.sh"


function usage {
    errcho "Usage: <compile> [options] <solution-path>"
    errcho "Options:"

    errcho -e "  -h, --help"
	errcho -e "\tShows this help."

    errcho -e "  -v, --verbose"
	errcho -e "\tPrints verbose details on values, decisions, and commands being executed."

    errcho -e "  -p, --public"
    errcho -e "\tUses the public graders for compiling the solution."
}

if "${HAS_GRADER}"; then
    GRADER_TYPE="judge"
    USED_GRADER_DIR="${GRADER_DIR}"
fi

VERBOSE=false

function handle_option {
    shifts=0
    case "${curr}" in
        -h|--help)
            usage
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            ;;
        -p|--public)
            if "${HAS_GRADER}"; then
                GRADER_TYPE="public"
                USED_GRADER_DIR="${PUBLIC_DIR}"
            else
                errcho "Grader is not supported."
                exit 2
            fi
            ;;
        *)
            invalid_arg "undefined option"
            ;;
    esac
}

function handle_positional_arg {
    if variable_not_exists "SOLUTION" ; then
        SOLUTION="${curr}"
        return
    fi
    invalid_arg "meaningless argument"
}

argument_parser "handle_positional_arg" "handle_option" "$@"

if variable_not_exists "SOLUTION" ; then
    errcho "Solution is not specified."
    usage
    exit 2
fi


# This function 'echo's its arguments iff VERBOSE is true
function vecho {
	if "${VERBOSE}" ; then
		cerrcho cyan "$@"
	fi
}

# This function runs a command
# It also prints the command before running iff VERBOSE is true
function vrun {
	if "${VERBOSE}" ; then
		cerrcho cyan -n "RUN: "
		errcho "$@"
	fi
	"$@"
}


sensitive check_file_exists "Solution file" "${SOLUTION}"


ext="$(extension "${SOLUTION}")"

if [ "${ext}" == "cpp" -o "${ext}" == "cc" ] ; then
	vecho "Detected language: C++"
	LANG="cpp"
elif [ "${ext}" == "pas" ] ; then
	vecho "Detected language: Pascal"
	LANG="pas"
elif [ "${ext}" == "java" ] ; then
	vecho "Detected language: Java"
	LANG="java"
else
    cerrcho red -n "Error: "
    errcho "Unknown solution extension: ${ext}"
    exit 1
fi

prog="${PROBLEM_NAME}.${LANG}"

if "${HAS_GRADER}"; then
    vecho "The task has grader."
	vecho "GRADER_TYPE='${GRADER_TYPE}'"
	vecho "USED_GRADER_DIR='${USED_GRADER_DIR}'"
    GRADER_LANG_DIR="${USED_GRADER_DIR}/${LANG}"
	vecho "GRADER_LANG_DIR='${GRADER_LANG_DIR}'"
else
   	vecho "The task does not have grader."
fi

vecho "Cleaning the sandbox..."
vrun recreate_dir "${SANDBOX}"

vecho "Copying solution '${SOLUTION}' to sandbox as '${prog}'..."
vrun cp "${SOLUTION}" "${SANDBOX}/${prog}"

vecho "Entering the sandbox."
pushd "${SANDBOX}" > /dev/null

if [ "${LANG}" == "cpp" ] ; then
    variable_not_exists "CPP_STD_OPT" && CPP_STD_OPT="--std=gnu++14"
    vecho "CPP_STD_OPT='${CPP_STD_OPT}'"
    variable_not_exists "CPP_WARNING_OPTS" && CPP_WARNING_OPTS="-Wall -Wextra -Wshadow"
    vecho "CPP_WARNING_OPTS='${CPP_WARNING_OPTS}'"
    variable_not_exists "CPP_OPTS" && CPP_OPTS="-DEVAL ${CPP_STD_OPT} ${CPP_WARNING_OPTS} -O2"
    vecho "CPP_OPTS='${CPP_OPTS}'"
	exe_file="${PROBLEM_NAME}.exe"
    if "${HAS_GRADER}"; then
	    grader_header="${PROBLEM_NAME}.h"
	    grader_cpp="grader.cpp"
    	vecho "Copying '${grader_header}' and '${grader_cpp}' to sandbox..."
        vrun cp "${GRADER_LANG_DIR}/${grader_header}" "${GRADER_LANG_DIR}/${grader_cpp}" "${SANDBOX}"
    	vecho "Compiling grader..."
        vrun g++ ${CPP_OPTS} -c "${grader_cpp}" -o "grader.o"
    	vecho "Removing grader source..."
        vrun rm "${grader_cpp}"
    	vecho "Compiling solution and linking with grader..."
        vrun g++ ${CPP_OPTS} "grader.o" "${prog}" -o "${exe_file}"
    else
    	vecho "Compiling and linking..."
        vrun g++ ${CPP_OPTS} "${prog}" -o "${exe_file}"
    fi
elif [ "${LANG}" == "pas" ] ; then
    variable_not_exists "PAS_OPTS" && PAS_OPTS="-dEVAL -XS -O2"
    vecho "PAS_OPTS='${PAS_OPTS}'"
    exe_file="${PROBLEM_NAME}.exe"
    if "${HAS_GRADER}"; then
	    grader_pas="grader.pas"
    	vecho "Copying '${grader_pas}' to sandbox..."
        vrun cp "${GRADER_LANG_DIR}/${grader_pas}" "${SANDBOX}"
		graderlib="graderlib.pas"
        if [ -f "${GRADER_LANG_DIR}/${graderlib}" ] ; then
	    	vecho "Copying '${graderlib}' to sandbox..."
        	vrun cp "${GRADER_LANG_DIR}/${graderlib}" "${SANDBOX}"
        fi
    	vecho "Compiling and linking..."
        vrun fpc ${PAS_OPTS} "${grader_pas}" "-o${exe_file}"
    else
    	vecho "Compiling and linking..."
        vrun fpc ${PAS_OPTS} "${prog}" "-o${exe_file}"
    fi
elif [ "${LANG}" == "java" ] ; then
    variable_not_exists "JAVAC_OPTS" && JAVAC_OPTS=""
    vecho "JAVAC_OPTS='${JAVAC_OPTS}'"
	jar_file="${PROBLEM_NAME}.jar"
    if "${HAS_GRADER}"; then
		grader_java="grader.java"
    	vecho "Copying '${grader_java}' to sandbox..."
        vrun cp "${GRADER_LANG_DIR}/${grader_java}" "${SANDBOX}"
    	vecho "Compiling java sources..."
        vrun javac ${JAVAC_OPTS} "${grader_java}" "${prog}"
    	vecho "Creating the jar file..."
        vrun jar cfe "${jar_file}" "grader" *.class
    else
    	vecho "Compiling java sources..."
        vrun javac ${JAVAC_OPTS} "${prog}"
    	vecho "Creating the jar file..."
        vrun jar cfe "${jar_file}" "${PROBLEM_NAME}" *.class
    fi
	vecho "Removing *.class files..."
    vrun rm *.class
else
    cerrcho red "Illegal state: unknown language: ${LANG}"
    exit 1
fi

vecho "Exiting the sandbox."
popd > /dev/null


function replace_tokens {
	the_file="$1"
    vrun sed -i'' -e "s/PROBLEM_NAME_PLACE_HOLDER/${PROBLEM_NAME}/g" "${the_file}"
}

execsh_name="exec.sh"
execsh="${SANDBOX}/${execsh_name}"
vecho "Creating '${execsh_name}' in sandbox..."
vrun cp "${TEMPLATES}/exec.${LANG}.sh" "${execsh}"
replace_tokens "${execsh}"
vrun chmod +x "${execsh}"

if "${HAS_GRADER}"; then
    source_runsh="${TEMPLATES}/run.${GRADER_TYPE}.sh"
else
    source_runsh="${TEMPLATES}/run.judge.sh"
fi

runsh_name="run.sh"
runsh="${SANDBOX}/${runsh_name}"
vecho "Creating '${runsh_name}' in sandbox..."
vrun cp "${source_runsh}" "${runsh}"
replace_tokens "${runsh}"
vrun chmod +x "${runsh}"


post_compile_name="post_compile.sh"
post_compile="${TEMPLATES}/${post_compile_name}"

if [ -f "${post_compile}" ] ; then
    if "${HAS_GRADER}"; then
        export GRADER_TYPE
        export USED_GRADER_DIR
        export GRADER_LANG_DIR
    fi
    export SOLUTION
	vecho "File ${post_compile_name} is present in templates. Executing..."
    vrun bash "${post_compile}"
else
	vecho "File ${post_compile_name} is not present in templates. Nothing more to do."
fi

cecho green OK
