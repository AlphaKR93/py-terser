"""Tests for CLI size-based output selection (best effort) functionality."""
import os
import sys
import tempfile

from subprocess_compat import run_subprocess, safe_decode


def test_returns_minified_when_smaller():
    """Test CLI returns minified output when it's smaller than original."""
    code = '''
def hello_world():
    """A simple function."""
    print("Hello, world!")
    return None

if __name__ == "__main__":
    hello_world()
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_file = f.name

    try:
        env = os.environ.copy()
        env.pop('PYMINIFY_FORCE_BEST_EFFORT', None)

        result = run_subprocess([
            sys.executable, '-m', 'terser', temp_file
        ], timeout=30, env=env)

        assert result.returncode == 0

        stdout_text = safe_decode(result.stdout)
        assert len(stdout_text) < len(code)

    finally:
        os.unlink(temp_file)


def test_returns_original_when_longer():
    """Test CLI returns original code when minified output would be longer."""
    code = 'True if 0in x else False'

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_file = f.name

    try:
        env = os.environ.copy()
        env.pop('PYMINIFY_FORCE_BEST_EFFORT', None)

        result = run_subprocess([
            sys.executable, '-m', 'terser', temp_file
        ], timeout=30, env=env)

        assert result.returncode == 0

        stdout_text = safe_decode(result.stdout)
        assert stdout_text == code

    finally:
        os.unlink(temp_file)


def test_force_minified_with_env_var():
    """Test environment variable forces minified output regardless of size."""
    code = 'True if 0in x else False'
    expected_output = 'True if 0 in x else False'

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_file = f.name

    try:
        env = os.environ.copy()
        env['PYMINIFY_FORCE_BEST_EFFORT'] = '1'

        result = run_subprocess([
            sys.executable, '-m', 'terser', temp_file
        ], timeout=30, env=env)

        assert result.returncode == 0

        stdout_text = safe_decode(result.stdout)
        assert stdout_text == expected_output

    finally:
        os.unlink(temp_file)


def test_stdin_behavior():
    """Test size-based logic works with stdin input."""
    code = 'True if 0in x else False'
    expected_output = 'True if 0 in x else False'

    # Without env var - should return original
    env = os.environ.copy()
    env.pop('PYMINIFY_FORCE_BEST_EFFORT', None)

    result = run_subprocess([
        sys.executable, '-m', 'terser', '-'
    ], input_data=code, timeout=30, env=env)

    assert result.returncode == 0
    stdout_text = safe_decode(result.stdout)
    assert stdout_text == code

    # With env var - should return minified
    env['PYMINIFY_FORCE_BEST_EFFORT'] = '1'

    result = run_subprocess([
        sys.executable, '-m', 'terser', '-'
    ], input_data=code, timeout=30, env=env)

    assert result.returncode == 0
    stdout_text = safe_decode(result.stdout)
    assert stdout_text == expected_output


def test_output_file_behavior():
    """Test size-based logic works with --output flag."""
    code = 'True if 0in x else False'

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as input_file:
        input_file.write(code)
        input_filename = input_file.name

    with tempfile.NamedTemporaryFile(delete=False) as output_file:
        output_filename = output_file.name

    try:
        env = os.environ.copy()
        env.pop('PYMINIFY_FORCE_BEST_EFFORT', None)

        result = run_subprocess([
            sys.executable, '-m', 'terser',
            input_filename, '--output', output_filename
        ], timeout=30, env=env)

        assert result.returncode == 0

        with open(output_filename, 'r') as f:
            output_content = f.read()

        assert output_content == code

    finally:
        os.unlink(input_filename)
        os.unlink(output_filename)


def test_in_place_behavior():
    """Test size-based logic works with --in-place flag."""
    code = 'True if 0in x else False'

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_file = f.name

    try:
        env = os.environ.copy()
        env.pop('PYMINIFY_FORCE_BEST_EFFORT', None)

        result = run_subprocess([
            sys.executable, '-m', 'terser',
            temp_file, '--in-place'
        ], timeout=30, env=env)

        assert result.returncode == 0

        with open(temp_file, 'r') as f:
            modified_content = f.read()

        assert modified_content == code

    finally:
        os.unlink(temp_file)


def test_directory_output_and_reachability():
    """Test minifying multiple directories to an output directory, and verifying reachability prunes unused files."""
    with tempfile.TemporaryDirectory() as src_dir:
        src_path = os.path.join(src_dir, 'src')
        vendor_path = os.path.join(src_dir, '_vendor')
        os.makedirs(src_path)
        os.makedirs(vendor_path)
        
        app_code = "from my_vendor import used_func\nused_func()"
        with open(os.path.join(src_path, 'app.py'), 'w') as f:
            f.write(app_code)
            
        vendor_code = "def used_func():\n    pass"
        with open(os.path.join(vendor_path, 'my_vendor.py'), 'w') as f:
            f.write(vendor_code)
            
        unused_code = "def unused_func():\n    pass"
        with open(os.path.join(vendor_path, 'unused_vendor.py'), 'w') as f:
            f.write(unused_code)
            
        out_dir = os.path.join(src_dir, 'out')
        
        env = os.environ.copy()
        env['PYMINIFY_FORCE_BEST_EFFORT'] = '1'
        
        result = run_subprocess([
            sys.executable, '-m', 'terser',
            src_path, vendor_path, '--output', out_dir
        ], timeout=30, env=env)
        
        assert result.returncode == 0
        out_files = os.listdir(out_dir)
        assert len(out_files) == 2
        for filename in out_files:
            assert 'unused_vendor' not in filename


def test_in_place_reachability():
    """Test that --in-place deletes unused modules."""
    with tempfile.TemporaryDirectory() as src_dir:
        src_path = os.path.join(src_dir, 'src')
        vendor_path = os.path.join(src_dir, '_vendor')
        os.makedirs(src_path)
        os.makedirs(vendor_path)
        
        app_code = "from my_vendor import used_func\nused_func()"
        app_file = os.path.join(src_path, 'app.py')
        with open(app_file, 'w') as f:
            f.write(app_code)
            
        vendor_code = "def used_func():\n    pass"
        vendor_file = os.path.join(vendor_path, 'my_vendor.py')
        with open(vendor_file, 'w') as f:
            f.write(vendor_code)
            
        unused_file = os.path.join(vendor_path, 'unused_vendor.py')
        unused_code = "def unused_func():\n    pass"
        with open(unused_file, 'w') as f:
            f.write(unused_code)
            
        env = os.environ.copy()
        env['PYMINIFY_FORCE_BEST_EFFORT'] = '1'
        
        result = run_subprocess([
            sys.executable, '-m', 'terser',
            src_path, vendor_path, '--in-place'
        ], timeout=30, env=env)
        
        assert result.returncode == 0
        src_files = os.listdir(src_path)
        assert len(src_files) == 1
        vendor_files = os.listdir(vendor_path)
        assert len(vendor_files) == 1
        assert 'unused_vendor.py' not in vendor_files


def test_large_number_of_components():
    """Test that cli can handle a very large number of top-level names without raising StopIteration."""
    classes = [f"class Class{i}:\n    pass" for i in range(3000)]
    code = "\n".join(classes)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_file = f.name
        
    try:
        env = os.environ.copy()
        env['PYMINIFY_FORCE_BEST_EFFORT'] = '1'
        
        result = run_subprocess([
            sys.executable, '-m', 'terser',
            temp_file, '--output', temp_file + '.out'
        ], timeout=60, env=env)
        
        assert result.returncode == 0
        assert os.path.exists(temp_file + '.out')
    finally:
        os.unlink(temp_file)
        if os.path.exists(temp_file + '.out'):
            os.unlink(temp_file + '.out')
