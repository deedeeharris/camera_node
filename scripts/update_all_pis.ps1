# PowerShell script to SSH into multiple IPs and run a script

# Array of IP addresses
$ipAddresses = @(
    "192.168.195.57",
    "192.168.195.73",
    "192.168.195.70",
    "192.168.195.56"
)

# Username for SSH connection
$username = "user"  # Change this to your Raspberry Pi username

# Loop through each IP address
foreach ($ip in $ipAddresses) {
    Write-Host "Connecting to $ip..." -ForegroundColor Green

    # Prompt for password (securely)
    $password = Read-Host "Enter password for $username@$ip" -AsSecureString

    try {
        # Construct the SSH command.  Crucially, use -t to allocate a pseudo-terminal.
        # This is often *required* for sudo to work correctly over SSH.
        $sshCommand = "ssh -t $username@$ip 'sudo ./get_repo_updates.sh'"

        # Convert the SecureString password to a plain text string (necessary for ssh.exe)
        $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))

        # Create a new process to run the SSH command
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo.FileName = "ssh"
        $process.StartInfo.Arguments = "-t $username@$ip sudo ./get_repo_updates.sh"  # -t for pseudo-terminal
        $process.StartInfo.RedirectStandardInput = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        $process.StartInfo.UseShellExecute = $false  # Required for redirection
        $process.StartInfo.CreateNoWindow = $true

        # Start the SSH process
        $process.Start() | Out-Null # Start-Process doesn't return the process object directly

        # Pass the password to the SSH process's standard input
        $process.StandardInput.WriteLine($plainPassword)
        $process.StandardInput.Close()


        # Capture and display the output and error streams
        $output = $process.StandardOutput.ReadToEnd()
        $error = $process.StandardError.ReadToEnd()

        # Wait for the process to exit
        $process.WaitForExit()

        # Display the output.  Use $($ip) for correct variable expansion within the string.
        Write-Host "Output from $($ip):" -ForegroundColor Cyan
        Write-Host $output
        if ($error) {
          Write-Host "Error from $($ip):" -ForegroundColor Red
          Write-Host $error
        }


        Write-Host "Finished with $ip" -ForegroundColor Green

    }
    catch {
        # Use $($_.Exception.Message) for correct error message display.
        Write-Host "An error occurred connecting to $($ip): $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "Script completed." -ForegroundColor Yellow