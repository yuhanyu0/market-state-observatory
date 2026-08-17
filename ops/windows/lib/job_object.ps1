Set-StrictMode -Version 2.0

$script:MsoJobObjectVersion = '0.4.5'

function Initialize-MsoJobObjectInterop {
    [CmdletBinding()]
    param()

    if (-not ('MarketStateObservatory.Windows.OwnedProcess' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Collections;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

namespace MarketStateObservatory.Windows
{
    public sealed class OwnedProcessResult
    {
        public int ExitCode { get; set; }
        public string Stdout { get; set; }
        public string Stderr { get; set; }
    }

    public sealed class OwnedProcess : IDisposable
    {
        private const uint CREATE_SUSPENDED = 0x00000004;
        private const uint CREATE_NO_WINDOW = 0x08000000;
        private const uint CREATE_UNICODE_ENVIRONMENT = 0x00000400;
        private const uint STARTF_USESTDHANDLES = 0x00000100;
        private const uint HANDLE_FLAG_INHERIT = 0x00000001;
        private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
        private const uint JOB_OBJECT_TERMINATE = 0x0008;
        private const uint JOB_OBJECT_QUERY = 0x0004;
        private const uint PROCESS_QUERY_LIMITED_INFORMATION = 0x1000;
        private const uint INFINITE = 0xffffffff;
        private const int JobObjectExtendedLimitInformation = 9;

        [StructLayout(LayoutKind.Sequential)]
        private struct SECURITY_ATTRIBUTES
        {
            public int nLength;
            public IntPtr lpSecurityDescriptor;
            [MarshalAs(UnmanagedType.Bool)] public bool bInheritHandle;
        }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct STARTUPINFO
        {
            public int cb;
            public string lpReserved;
            public string lpDesktop;
            public string lpTitle;
            public uint dwX;
            public uint dwY;
            public uint dwXSize;
            public uint dwYSize;
            public uint dwXCountChars;
            public uint dwYCountChars;
            public uint dwFillAttribute;
            public uint dwFlags;
            public short wShowWindow;
            public short cbReserved2;
            public IntPtr lpReserved2;
            public IntPtr hStdInput;
            public IntPtr hStdOutput;
            public IntPtr hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct PROCESS_INFORMATION
        {
            public IntPtr hProcess;
            public IntPtr hThread;
            public uint dwProcessId;
            public uint dwThreadId;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct IO_COUNTERS
        {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateJobObject(IntPtr attributes, string name);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenJobObject(uint access, bool inheritHandle, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetInformationJobObject(
            IntPtr job, int informationClass, IntPtr information, uint informationLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool TerminateJobObject(IntPtr job, uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool result);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(uint access, bool inheritHandle, uint processId);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetProcessTimes(
            IntPtr process, out long creation, out long exitTime, out long kernelTime, out long userTime);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CreateProcess(
            string applicationName,
            StringBuilder commandLine,
            IntPtr processAttributes,
            IntPtr threadAttributes,
            [MarshalAs(UnmanagedType.Bool)] bool inheritHandles,
            uint creationFlags,
            IntPtr environment,
            string currentDirectory,
            ref STARTUPINFO startupInfo,
            out PROCESS_INFORMATION processInformation);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CreatePipe(
            out IntPtr readPipe, out IntPtr writePipe,
            ref SECURITY_ATTRIBUTES attributes, uint size);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool SetHandleInformation(IntPtr handle, uint mask, uint flags);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern uint ResumeThread(IntPtr thread);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CloseHandle(IntPtr handle);

        private IntPtr _job;
        private IntPtr _process;
        private IntPtr _thread;
        private StreamReader _stdoutReader;
        private StreamReader _stderrReader;
        private Task<string> _stdoutTask;
        private Task<string> _stderrTask;
        private bool _resumed;
        private bool _disposed;

        public int ProcessId { get; private set; }
        public string JobName { get; private set; }

        private static void ThrowLastError(string operation)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), operation);
        }

        private static IntPtr NewPipe(out IntPtr childWrite)
        {
            SECURITY_ATTRIBUTES attributes = new SECURITY_ATTRIBUTES();
            attributes.nLength = Marshal.SizeOf(typeof(SECURITY_ATTRIBUTES));
            attributes.bInheritHandle = true;
            IntPtr parentRead;
            if (!CreatePipe(out parentRead, out childWrite, ref attributes, 0))
                ThrowLastError("CreatePipe failed");
            if (!SetHandleInformation(parentRead, HANDLE_FLAG_INHERIT, 0))
            {
                CloseHandle(parentRead);
                CloseHandle(childWrite);
                ThrowLastError("SetHandleInformation failed");
            }
            return parentRead;
        }

        private static IntPtr BuildEnvironment(IDictionary additions, IEnumerable removals)
        {
            SortedDictionary<string, string> values =
                new SortedDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (DictionaryEntry item in Environment.GetEnvironmentVariables())
                values[(string)item.Key] = item.Value == null ? "" : item.Value.ToString();
            if (removals != null)
                foreach (object name in removals)
                    if (name != null) values.Remove(name.ToString());
            if (additions != null)
                foreach (DictionaryEntry item in additions)
                    values[(string)item.Key] = item.Value == null ? "" : item.Value.ToString();
            StringBuilder block = new StringBuilder();
            foreach (KeyValuePair<string, string> item in values)
                block.Append(item.Key).Append('=').Append(item.Value).Append('\0');
            block.Append('\0');
            return Marshal.StringToHGlobalUni(block.ToString());
        }

        public static OwnedProcess StartSuspended(
            string fileName,
            string arguments,
            string workingDirectory,
            IDictionary childEnvironment,
            IEnumerable removeEnvironment,
            string jobName)
        {
            if (String.IsNullOrWhiteSpace(fileName)) throw new ArgumentNullException("fileName");
            if (String.IsNullOrWhiteSpace(jobName)) throw new ArgumentNullException("jobName");
            OwnedProcess owned = new OwnedProcess();
            owned.JobName = jobName;
            IntPtr stdoutRead = IntPtr.Zero;
            IntPtr stdoutWrite = IntPtr.Zero;
            IntPtr stderrRead = IntPtr.Zero;
            IntPtr stderrWrite = IntPtr.Zero;
            IntPtr environment = IntPtr.Zero;
            try
            {
                owned._job = CreateJobObject(IntPtr.Zero, jobName);
                if (owned._job == IntPtr.Zero) ThrowLastError("CreateJobObject failed");
                if (!SetHandleInformation(owned._job, HANDLE_FLAG_INHERIT, 0))
                    ThrowLastError("Job handle inheritance control failed");
                JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits =
                    new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
                limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                int limitSize = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
                IntPtr limitPointer = Marshal.AllocHGlobal(limitSize);
                try
                {
                    Marshal.StructureToPtr(limits, limitPointer, false);
                    if (!SetInformationJobObject(
                        owned._job, JobObjectExtendedLimitInformation,
                        limitPointer, (uint)limitSize))
                        ThrowLastError("SetInformationJobObject failed");
                }
                finally { Marshal.FreeHGlobal(limitPointer); }

                stdoutRead = NewPipe(out stdoutWrite);
                stderrRead = NewPipe(out stderrWrite);
                STARTUPINFO startup = new STARTUPINFO();
                startup.cb = Marshal.SizeOf(typeof(STARTUPINFO));
                startup.dwFlags = STARTF_USESTDHANDLES;
                startup.hStdInput = IntPtr.Zero;
                startup.hStdOutput = stdoutWrite;
                startup.hStdError = stderrWrite;
                environment = BuildEnvironment(childEnvironment, removeEnvironment);
                string command = "\"" + fileName + "\"";
                if (!String.IsNullOrEmpty(arguments)) command += " " + arguments;
                PROCESS_INFORMATION information;
                if (!CreateProcess(
                    fileName, new StringBuilder(command), IntPtr.Zero, IntPtr.Zero, true,
                    CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
                    environment, workingDirectory, ref startup, out information))
                    ThrowLastError("CreateProcess failed");
                owned._process = information.hProcess;
                owned._thread = information.hThread;
                owned.ProcessId = checked((int)information.dwProcessId);
                if (!AssignProcessToJobObject(owned._job, owned._process))
                    ThrowLastError("AssignProcessToJobObject failed");

                CloseHandle(stdoutWrite);
                stdoutWrite = IntPtr.Zero;
                CloseHandle(stderrWrite);
                stderrWrite = IntPtr.Zero;
                FileStream stdoutStream = new FileStream(
                    new SafeFileHandle(stdoutRead, true), FileAccess.Read, 4096, false);
                stdoutRead = IntPtr.Zero;
                FileStream stderrStream = new FileStream(
                    new SafeFileHandle(stderrRead, true), FileAccess.Read, 4096, false);
                stderrRead = IntPtr.Zero;
                owned._stdoutReader = new StreamReader(stdoutStream, Encoding.UTF8, true);
                owned._stderrReader = new StreamReader(stderrStream, Encoding.UTF8, true);
                owned._stdoutTask = owned._stdoutReader.ReadToEndAsync();
                owned._stderrTask = owned._stderrReader.ReadToEndAsync();
                return owned;
            }
            catch
            {
                owned.Dispose();
                throw;
            }
            finally
            {
                if (environment != IntPtr.Zero) Marshal.ZeroFreeGlobalAllocUnicode(environment);
                if (stdoutRead != IntPtr.Zero) CloseHandle(stdoutRead);
                if (stdoutWrite != IntPtr.Zero) CloseHandle(stdoutWrite);
                if (stderrRead != IntPtr.Zero) CloseHandle(stderrRead);
                if (stderrWrite != IntPtr.Zero) CloseHandle(stderrWrite);
            }
        }

        public void Resume()
        {
            if (_disposed) throw new ObjectDisposedException("OwnedProcess");
            if (_resumed) return;
            uint result = ResumeThread(_thread);
            if (result == 0xffffffff) ThrowLastError("ResumeThread failed");
            _resumed = true;
        }

        public OwnedProcessResult WaitForExit()
        {
            if (!_resumed) throw new InvalidOperationException("Process is still suspended");
            uint wait = WaitForSingleObject(_process, INFINITE);
            if (wait != 0) ThrowLastError("WaitForSingleObject failed");
            uint code;
            if (!GetExitCodeProcess(_process, out code)) ThrowLastError("GetExitCodeProcess failed");
            Task.WaitAll(_stdoutTask, _stderrTask);
            return new OwnedProcessResult
            {
                ExitCode = unchecked((int)code),
                Stdout = _stdoutTask.Result,
                Stderr = _stderrTask.Result
            };
        }

        public static bool TerminateNamedJob(string jobName, uint exitCode)
        {
            IntPtr job = OpenJobObject(JOB_OBJECT_TERMINATE, false, jobName);
            if (job == IntPtr.Zero) return false;
            try
            {
                if (!TerminateJobObject(job, exitCode)) ThrowLastError("TerminateJobObject failed");
                return true;
            }
            finally { CloseHandle(job); }
        }

        public static bool IsProcessInNamedJob(int processId, string jobName)
        {
            IntPtr job = OpenJobObject(JOB_OBJECT_QUERY, false, jobName);
            if (job == IntPtr.Zero) return false;
            IntPtr process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, (uint)processId);
            if (process == IntPtr.Zero) { CloseHandle(job); return false; }
            try
            {
                bool result;
                if (!IsProcessInJob(process, job, out result))
                    ThrowLastError("IsProcessInJob failed");
                return result;
            }
            finally
            {
                CloseHandle(process);
                CloseHandle(job);
            }
        }

        public static string GetProcessCreatedAtUtc(int processId)
        {
            IntPtr process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, (uint)processId);
            if (process == IntPtr.Zero) return null;
            try
            {
                long creation;
                long exitTime;
                long kernelTime;
                long userTime;
                if (!GetProcessTimes(process, out creation, out exitTime, out kernelTime, out userTime))
                    ThrowLastError("GetProcessTimes failed");
                return DateTime.FromFileTimeUtc(creation).ToString("o");
            }
            finally { CloseHandle(process); }
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            if (_job != IntPtr.Zero) { CloseHandle(_job); _job = IntPtr.Zero; }
            if (_thread != IntPtr.Zero) { CloseHandle(_thread); _thread = IntPtr.Zero; }
            if (_process != IntPtr.Zero) { CloseHandle(_process); _process = IntPtr.Zero; }
            if (_stdoutReader != null) _stdoutReader.Dispose();
            if (_stderrReader != null) _stderrReader.Dispose();
        }
    }
}
'@
    }
}

function New-MsoOwnedProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$RawArguments,
        [hashtable]$ChildEnvironment = @{},
        [string[]]$RemoveEnvironment = @(),
        [Parameter(Mandatory = $true)][string]$JobName
    )
    Initialize-MsoJobObjectInterop
    return [MarketStateObservatory.Windows.OwnedProcess]::StartSuspended(
        $FileName,
        $RawArguments,
        $WorkingDirectory,
        $ChildEnvironment,
        [string[]]$RemoveEnvironment,
        $JobName
    )
}

function Stop-MsoNamedJob {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$JobName)
    Initialize-MsoJobObjectInterop
    return [MarketStateObservatory.Windows.OwnedProcess]::TerminateNamedJob($JobName, 197)
}

function Test-MsoProcessInNamedJob {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$JobName
    )
    Initialize-MsoJobObjectInterop
    return [MarketStateObservatory.Windows.OwnedProcess]::IsProcessInNamedJob($ProcessId, $JobName)
}

function Get-MsoNativeProcessCreatedAtUtc {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    Initialize-MsoJobObjectInterop
    return [MarketStateObservatory.Windows.OwnedProcess]::GetProcessCreatedAtUtc($ProcessId)
}
