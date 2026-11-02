"""Compile the production FD predicate with bounded readlinkat responses."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "loader/src/injector/module.cpp").read_text()
start = source.index("static bool is_trace_marker_fd(")
end = source.index("\nvoid ZygiskContext::sanitize_fds()", start)
predicate = source[start:end]

prefix = r"""
#include <algorithm>
#include <cassert>
#include <cstring>
#include <iostream>
#include <string>
#include <sys/types.h>
static std::string target;
static bool fail_lookup;
static ssize_t fake_readlinkat(int directory,const char *name,char *buf,size_t size) {
    assert(directory==42 && name && *name);
    if(fail_lookup)return -1;
    size_t n=std::min(size,target.size());
    memcpy(buf,target.data(),n);
    return static_cast<ssize_t>(n);
}
#define readlinkat fake_readlinkat
"""
suffix = r"""
#undef readlinkat
int main() {
    for(const char *path:{"/sys/kernel/tracing/trace_marker",
                         "/sys/kernel/debug/tracing/trace_marker"}) {
        target=path;
        for(const char *fd:{"97","100","310"})assert(is_trace_marker_fd(42,fd));
    }
    for(const char *path:{"", "pipe:[123]", "anon_inode:[eventpoll]", "/dev/null",
                         "/tmp/trace_marker", "/sys/kernel/tracing/trace_marker_raw",
                         "/sys/kernel/debug/tracing/trace_marker/",
                         "/sys/kernel/debug/tracing/trace_marker-extra"}) {
        target=path;
        assert(!is_trace_marker_fd(42,"100"));
    }
    target=std::string(4096,'x');
    assert(!is_trace_marker_fd(42,"97"));
    target="/sys/kernel/tracing/trace_marker";
    fail_lookup=true;
    assert(!is_trace_marker_fd(42,"310"));
    std::cout<<"PASS: marker paths, arbitrary FD numbers, unrelated targets, "
                "near matches, truncation and lookup failures\n";
}
"""

with tempfile.TemporaryDirectory(prefix="neozygisk-fd-test-") as temporary:
    directory = Path(temporary)
    test_source = directory / "test.cpp"
    binary = directory / "test"
    test_source.write_text(prefix + predicate + suffix)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    str(test_source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
